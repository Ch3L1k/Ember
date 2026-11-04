/* Ember — Copyright (C) 2026 Ember contributors.
 * GNU GPL version 3 or later; distributed without any warranty.
 * See LICENSE for the full license and warranty disclaimer.
 */
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const net = require('node:net');
const cp = require('node:child_process');
const assert = require('node:assert/strict');
const http = require('node:http');

function fetch(url, options = {}) {
  return new Promise((resolve, reject) => {
    const headers = { ...options.headers };
    if (options.body) headers['Content-Length'] = Buffer.byteLength(options.body);
    const request = http.request(url, { method: options.method || 'GET', headers }, response => {
      const chunks = [];
      response.on('data', chunk => chunks.push(chunk));
      response.on('end', () => {
        const text = Buffer.concat(chunks).toString('utf8');
        resolve({ status: response.statusCode, ok: response.statusCode >= 200 && response.statusCode < 300, json: async () => JSON.parse(text), text: async () => text });
      });
    });
    request.setTimeout(20000, () => request.destroy(new Error('HTTP request timeout')));
    request.on('error', reject);
    if (options.body) request.write(options.body);
    request.end();
  });
}

const project = path.resolve(__dirname, '..');
const labRoot = path.resolve(process.env.EMBER_TEST_ROOT || path.join(project, 'ember-runtime', 'test'));
const python = path.join(project, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const reportDir = path.resolve(process.env.EMBER_TEST_REPORT || path.join(project, 'ember-runtime', 'report'));
const report = { started: new Date().toISOString(), environment: 'isolated headless Chromium and fixture Steam directory', checks: [], browserErrors: [], rpcErrors: [] };
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
let backend, browser, info;

async function availablePort() {
  const server = net.createServer();
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  await new Promise(resolve => server.close(resolve));
  return port;
}

async function check(name, action) {
  await action();
  report.checks.push({ name, ok: true });
  console.log('PASS ' + name);
}

async function rpc(method, args = []) {
  const response = await fetch(info.origin + '/api/call', { method: 'POST', headers: { Authorization: 'Bearer ' + info.token, 'Content-Type': 'application/json' }, body: JSON.stringify({ method, args }) });
  const payload = await response.json();
  return { status: response.status, ...payload };
}

async function run() {
  fs.mkdirSync(reportDir, { recursive: true });
  const prepared = cp.spawnSync(python, ['-m', 'lab.prepare', '--root', labRoot], { cwd: project, encoding: 'utf8', windowsHide: true });
  if (prepared.status) throw new Error(prepared.stderr || prepared.stdout);
  const fixture = JSON.parse(prepared.stdout.trim());
  const cdpPort = await availablePort();
  const runtimeFile = path.join(fixture.data, 'runtime.json');
  if (fs.existsSync(runtimeFile)) fs.unlinkSync(runtimeFile);
  const log = fs.openSync(path.join(reportDir, 'backend.log'), 'w');
  backend = cp.spawn(python, ['Ember.py'], { cwd: project, windowsHide: true, stdio: ['ignore', log, log], env: { ...process.env, EMBER_MODE: 'lab', EMBER_LAB_ROOT: fixture.root, EMBER_STEAM_DIR: fixture.steam, EMBER_DATA_DIR: fixture.data, EMBER_CDP_PORTS: String(cdpPort), APPDATA: path.join(fixture.root, 'AppData/Roaming'), LOCALAPPDATA: path.join(fixture.root, 'AppData/Local'), QT_QPA_PLATFORM: 'offscreen' } });
  backend.on('error', error => console.error(error));
  for (let attempt = 0; attempt < 100; attempt++) {
    if (fs.existsSync(runtimeFile)) {
      info = JSON.parse(fs.readFileSync(runtimeFile, 'utf8'));
      try { if ((await fetch(info.origin + '/health')).ok) break; } catch {}
    }
    if (backend.exitCode !== null) throw new Error('Backend exited: ' + fs.readFileSync(path.join(reportDir, 'backend.log'), 'utf8').slice(-3000));
    await delay(200);
  }
  assert(info, 'Backend did not create runtime info');
  await rpc('ember_set_language',['ru']);
  browser = await chromium.launch({ headless: true, args: ['--remote-debugging-port=' + cdpPort, '--remote-debugging-address=127.0.0.1'] });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, locale: 'ru-RU' });
  await context.route('**/*', route => route.request().url().startsWith(info.origin + '/') || route.request().url().startsWith('data:') ? route.continue() : route.abort());
  const page = await context.newPage();
  if(process.env.EMBER_ADD_UI_ONLY){
    await require('./check_additions.cjs')({context,info,project,reportDir,check,rpc});
    await require('./check_language.cjs')({context,info,project,reportDir,check,rpc});
    report.ok=true;return;
  }
  if(process.env.EMBER_ADAPTER_ONLY){
    await require('./check_millennium.cjs')({context,info,project,reportDir,check,rpc});
    await require('./check_cross_window.cjs')({context,info,project,reportDir,check,rpc});
    report.ok=true;
    return;
  }
  if(process.env.EMBER_LIBRARY_ONLY){
    await require('./check_library.cjs')({context,info,project,reportDir,check,rpc});
    report.ok=true;return;
  }
  page.on('pageerror', error => report.browserErrors.push(error.message));
  page.on('console', message => { if (message.type() === 'error' && !message.text().includes('net::ERR_FAILED')) report.browserErrors.push(message.text()); });
  page.on('response', response => { if (response.url().includes('/api/') && response.status() >= 400) report.rpcErrors.push({ status: response.status(), path: new URL(response.url()).pathname, method: response.request().postDataJSON()?.method }); });
  await page.goto(info.origin + '/lab/client.html');
  await check('Unauthenticated API access is rejected', async () => assert.equal((await fetch(info.origin + '/api/info')).status, 401));
  await check('Cross-origin backend commands are rejected', async () => {
    const response = await fetch(info.origin + '/api/call', { method: 'POST', headers: { Authorization: 'Bearer ' + info.token, Origin: 'https://untrusted.example', 'Content-Type': 'application/json' }, body: JSON.stringify({ method: 'get_app_version', args: [] }) });
    assert.equal(response.status, 403);
  });
  await check('Lab cannot restart or change the real Steam', async () => {
    for (const method of ['restart_steam', 'install_lumacore', 'open_file_dialog']) {
      const result = await rpc(method, method === 'install_lumacore' ? [fixture.steam, 'release'] : []);
      assert.equal(result.status, 403, method + ': ' + JSON.stringify(result));
    }
  });
  await check('Library contains only the isolated fixture game', async () => {
    const result = await rpc('get_installed_games');
    assert.equal(result.status, 200);
    const games = JSON.parse(result.result);
    assert.equal(games.length, 1);
    assert.equal(games[0].name, 'Ember Demo');
    assert(games[0].path.startsWith(fixture.root));
  });
  await check('Own UI integration attaches to the lab client', async () => page.waitForFunction(() => !!window.__emberSteam, null, { timeout: 20000 }));
  const popupPromise = context.waitForEvent('page');
  await page.locator('#steam-menu').click();
  const popup = await popupPromise;
  await popup.waitForLoadState();
  await check('Ember appears in the Steam-style dropdown', async () => popup.locator('#ember-steam-menuitem').waitFor({ timeout: 20000 }));
  await check('Ember uses enabled menu colors in normal and hovered states',async()=>{
    await popup.mouse.move(330,305);
    const item=popup.locator('#ember-steam-menuitem');
    const reference=popup.getByRole('menuitem',{name:'Настройки',exact:true});
    const color=node=>getComputedStyle(node).color;
    assert.equal(await item.evaluate(color),await reference.evaluate(color));
    assert.equal(await item.getAttribute('aria-disabled'),'false');
    await item.hover();const hovered=await item.evaluate(color);
    await reference.hover();assert.equal(hovered,await reference.evaluate(color));
    await popup.mouse.move(330,305);
  });
  await popup.screenshot({ path: path.join(reportDir, 'menu.png') });
  await popup.locator('#ember-steam-menuitem').click();
  await popup.close();
  const frame = page.frameLocator('#ember-steam-panel iframe');
  await check('Menu opens Ember inside the client', async () => frame.locator('.ember-status[data-connected="true"]').waitFor({ timeout: 20000 }));
  await check('Home is branded Ember', async () => assert.equal(await frame.locator('.sidebar-title').innerText(), 'EMBER'));
  await check('Catalog is the initial screen and the duplicate overview is absent from navigation', async () => {
    await frame.locator('#page-store.active #store-grid .game-card').first().waitFor();
    assert.equal(await frame.locator('.sidebar-nav [data-page="home"]').count(),0);
    assert(await frame.locator('#page-home').isHidden());
  });
  await check('Quoted catalog metadata cannot inject markup or button attributes', async () => {
    const result=await page.locator('#ember-steam-panel iframe').contentFrame().locator('body').evaluate(()=>{
      const name='Game " onclick="window.__injected=1 <b>test</b>';
      const app_id='12"><img src=x onerror="window.__injected=1">';
      const game={app_id,name,image_url:'/ember/mark.svg'};
      const card=Components.createGameCard(game);
      const list=Components.createGameListItem(game);
      return {name:card.querySelector('.game-card-name').textContent,attribute:card.querySelector('.btn-download').dataset.name,unsafe:card.querySelectorAll('[onclick],[onerror],b,script').length+list.querySelectorAll('[onclick],[onerror],b,script').length,expected:name};
    });
    assert.equal(result.name,result.expected);
    assert.equal(result.attribute,result.expected);
    assert.equal(result.unsafe,0);
  });
  await check('Tools replaces the duplicate library and uses the fixture game list', async () => {
    await frame.locator('.nav-item[data-page="ember-tools"]').click();
    await frame.locator('#ember-tool-game option[value="900000001"]').waitFor({state:'attached'});
    assert.equal(await frame.locator('.sidebar-nav [data-page="library"]').count(),0);
    await frame.locator('#ember-diagnose').waitFor();
    assert.equal(await frame.locator('#page-ember-tools .ember-tool-panel').count(),2);
    assert(await frame.locator('#ember-dlc-install').isDisabled());
  });
  await check('Legacy library remains hidden and inactive', async () => {
    assert(await frame.locator('#page-library').isHidden());
    assert.equal(await frame.locator('#library-grid [data-action="play"]').count(),0);
  });
  await page.screenshot({path:path.join(reportDir,'tools.png')});
  await check('Catalog search returns isolated test games', async () => {
    await frame.locator('.nav-item[data-page="store"]').click();
    await frame.locator('#page-store').getByText('Ember Puzzle', { exact: true }).first().waitFor({ timeout: 15000 });
  });
  await delay(350);
  await page.screenshot({ path: path.join(reportDir, 'catalog.png') });
  await check('Only core sections appear in navigation', async () => {
    assert.deepEqual(await frame.locator('.sidebar-nav .nav-item[data-page]').evaluateAll(nodes => nodes.map(node => node.dataset.page)), ['store','ember-library','ember-tools','ember-settings','ember-about']);
    assert.equal(await frame.locator('#page-home [data-ember-route="fixgame"],#page-home [data-ember-route="cloudsaves"]').count(), 0);
  });
  await check('Removed download settings have no controls or save handlers', async () => {
    assert.equal(await frame.locator('#page-store #store-connect-banner').count(), 0);
    assert.equal(await frame.locator('#page-ember-settings #store-connect-banner').count(), 1);
    await frame.locator('.nav-item[data-page="ember-settings"]').click();
    await frame.locator('#ember-steam-path').waitFor();
    assert.equal(await frame.locator('#ember-speed-limit,#ember-parallel-downloads,#ember-download-preferences').count(),0);
    assert.equal(await frame.locator('#ember-steam-path').inputValue(),fixture.steam);
    assert.equal((await rpc('set_setting',['steam_path','C:/unexpected'])).status,403);
  });
  await delay(200);
  await page.screenshot({path:path.join(reportDir,'settings.png')});
  await check('Removed Downloads page cannot be reached through navigation or a stale route',async()=>{
    assert.equal(await frame.locator('.nav-item[data-page="downloads"]').count(),0);
    await frame.locator('body').evaluate(()=>App.navigateTo('downloads'));
    await frame.locator('#page-store.active').waitFor();
    assert.equal(await frame.locator('#page-downloads').isVisible(),false);
  });
  await check('Backup and restore change only a fixture save', async () => {
    const save = path.join(fixture.root, 'saves/demo.json');
    fs.writeFileSync(save, JSON.stringify({ level: 7, coins: 42 }));
    assert.equal((await rpc('ember_lab_backup')).status, 200);
    fs.writeFileSync(save, JSON.stringify({ level: 1 }));
    assert.equal((await rpc('ember_lab_restore')).status, 200);
    assert.deepEqual(JSON.parse(fs.readFileSync(save, 'utf8')), { level: 7, coins: 42 });
  });
  await check('Attribution and license are accessible', async () => {
    await frame.locator('.nav-item[data-page="ember-about"]').click();
    assert.match(await frame.locator('#page-ember-about').innerText(), /SteaMidra 6\.9\.1/);
    assert.equal((await fetch(info.origin + '/LICENSE')).status, 200);
    const profile=frame.getByRole('link',{name:'Ch3L1k',exact:true});
    assert.equal(await profile.getAttribute('href'),'https://github.com/Ch3L1k');
    let complete;
    const opened=new Promise(resolve=>complete=resolve);
    const handler=async route=>{
      const body=route.request().postDataJSON();
      if(body.method==='open_url'){complete(body.args[0]);return route.fulfill({json:{result:null}});}
      return route.continue();
    };
    await page.route(info.origin+'/api/call',handler);
    await profile.click();
    assert.equal(await opened,'https://github.com/Ch3L1k');
    await page.unroute(info.origin+'/api/call',handler);
  });
  await page.screenshot({ path: path.join(reportDir, 'about.png') });
  await check('Closing and reopening the panel creates no duplicate frame', async () => {
    await page.getByRole('button', { name: 'Закрыть ×' }).click();
    assert.equal(await page.locator('#ember-steam-panel').isVisible(), false);
    await page.evaluate(() => window.__emberSteam.open());
    assert.equal(await page.locator('#ember-steam-panel iframe').count(), 1);
  });
  await check('Integration tolerates another extension element', async () => {
    await page.evaluate(() => { const marker = document.createElement('div'); marker.id = 'millennium-fixture-marker'; document.body.append(marker); window.__emberSteam.refresh(); });
    assert.equal(await page.locator('#millennium-fixture-marker').count(), 1);
  });
  await check('Reload preserves authentication and the selected page', async()=>{
    await frame.locator('.nav-item[data-page="store"]').click();
    const child=page.frames().find(item=>item.url().startsWith(info.origin+'/')&&!item.url().includes('/lab/'));
    await child.evaluate(()=>location.reload());
    await frame.locator('.ember-status[data-connected="true"]').waitFor({timeout:15000});
    await frame.locator('#page-store.active #store-grid .game-card').first().waitFor();
    assert.equal(new URL(child.url()).hash,'');
  });
  await check('Connection status recovers after a temporary event-stream outage',async()=>{
    const pattern=info.origin+'/api/events**';
    const interrupt=route=>route.abort();
    await page.route(pattern,interrupt);
    await rpc('load_library');
    await frame.locator('.ember-status[data-connected="false"]').waitFor({timeout:10000});
    await page.unroute(pattern,interrupt);
    await rpc('load_library');
    await frame.locator('.ember-status[data-connected="true"]').waitFor({timeout:10000});
  });
  await check('Integration survives reloading the Steam-style host window',async()=>{
    await page.reload();
    await page.waitForFunction(()=>!!window.__emberSteam,null,{timeout:15000});
    await page.evaluate(()=>window.__emberSteam.open());
    await frame.locator('.ember-status[data-connected="true"]').waitFor({timeout:15000});
    assert.equal(await page.locator('#ember-steam-panel iframe').count(),1);
  });
  await check('Backend availability is distinct from Steam integration availability',async()=>{
    const liveInfo=await (await fetch(info.origin+'/api/info',{headers:{Authorization:'Bearer '+info.token}})).json();
    let attached=false;
    const fakeInfo=route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({...liveInfo,mode:'desktop',integration:{...liveInfo.integration,connected:attached,message:attached?'Подключено к Steam':'Ожидание Steam'}})});
    await page.route(info.origin+'/api/info',fakeInfo);
    await frame.locator('.nav-item[data-page="store"]').click();
    await frame.locator('.ember-status[data-steam-connected="false"]').getByText('Ожидание Steam',{exact:true}).waitFor({timeout:10000});
    attached=true;
    await frame.locator('.ember-status[data-steam-connected="true"]').getByText('Подключён к Steam',{exact:true}).waitFor({timeout:10000});
    await page.unroute(info.origin+'/api/info',fakeInfo);
  });
  await check('Frontend has no unhandled JavaScript errors', async () => assert.deepEqual(report.browserErrors, []));
  await check('Normal UI calls have no rejected RPC requests', async () => assert.deepEqual(report.rpcErrors, []));
  if(process.env.EMBER_REACT_BUNDLE) await require('./check_millennium.cjs')({context,info,project,reportDir,check,rpc});
  await require('./check_additions.cjs')({context,info,project,reportDir,check,rpc});
  await require('./check_tools.cjs')({context,info,project,reportDir,check,rpc});
  await require('./check_catalog.cjs')({context,info,project,reportDir,check,rpc});
  await require('./check_language.cjs')({context,info,project,reportDir,check,rpc});
  await require('./check_search.cjs')({context,info,project,reportDir,check,rpc});
  await rpc('ember_set_language',['ru']);
  await require('./check_store.cjs')({context,info,project,reportDir,check,rpc,hostPage:page});
  await require('./check_library.cjs')({context,info,project,reportDir,check,rpc});
  report.ok = true;
}

run().catch(error => {
  report.ok = false;
  report.error = error.stack || String(error);
  console.error(report.error);
  process.exitCode = 1;
}).finally(async () => {
  if (browser) await browser.close();
  if (backend && backend.exitCode === null) backend.kill();
  report.finished = new Date().toISOString();
  fs.mkdirSync(reportDir, { recursive: true });
  fs.writeFileSync(path.join(reportDir, process.env.EMBER_ADAPTER_ONLY?'millennium-checks.json':process.env.EMBER_LIBRARY_ONLY?'library-checks.json':'checks.json'), JSON.stringify(report, null, 2));
  console.log('Report: ' + path.join(reportDir, 'checks.json'));
});
