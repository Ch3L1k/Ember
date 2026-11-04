/* Ember — Copyright (C) 2026 Ember contributors.
 * GNU GPL version 3 or later; distributed without any warranty.
 * See LICENSE for the full license and warranty disclaimer.
 */
const path = require('node:path');
const assert = require('node:assert/strict');

module.exports = async function({context, info, project, reportDir, check, rpc}) {
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(info.origin + '/lab/millennium.html');
    await page.addScriptTag({path: process.env.EMBER_REACT_BUNDLE});
    await page.evaluate(() => {
        window.fixtureRoutes = new Map();
        window.fixtureConnection = {starting: true};
        window.fixtureCalls = [];
        window.fixtureRoot = window.emberCreateRoot(document.getElementById('route'));
        window.fixturePopup = document.createElement('iframe');
        window.fixturePopup.id = 'menu-fixture';
        window.fixturePopup.style.cssText = 'position:absolute;top:0;left:0;width:350px;height:270px;z-index:10';
        document.body.append(window.fixturePopup);
        const doc = window.fixturePopup.contentDocument;
        doc.open();
        doc.write('<title>Adapter menu</title><style>body{background:#3d4450;color:#969696;font:14px Arial;margin:0}.contextMenuItem{color:#dcdedf;padding:10px 16px}.contextMenuItem:hover{background:#353b45;color:white}</style><div id="millennium-menuitem" role="menuitem" class="contextMenuItem">Millennium</div><div role="menuitem" class="contextMenuItem">Восстановить файлы игры…</div><div role="menuitem" class="contextMenuItem">Настройки</div><div role="menuitem" class="contextMenuItem">Выход</div>');
        doc.close();
        window.fixtureHook = null;
        window.MILLENNIUM_API = {
            ffi: (_, method) => async (...args) => {
                window.fixtureCalls.push(method);
                if(method === 'get_connection') {
                    if(window.fixtureHangOnce){window.fixtureHangOnce=false;return new Promise(()=>{});}
                    const connection=window.fixtureConnection;
                    if(connection.origin){
                        const value=await (await fetch(connection.origin+'/api/store-add',{headers:{Authorization:'Bearer '+connection.token}})).json();
                        connection.add_request=value.request;
                    }
                    return connection;
                }
                if(method === 'acknowledge_store_add') return (await (await fetch(window.fixtureConnection.origin+'/api/store-add',{method:'POST',headers:{Authorization:'Bearer '+window.fixtureConnection.token,'Content-Type':'application/json'},body:JSON.stringify({action:'acknowledge',request_id:args[0]})})).json()).success;
                if(method === 'start_backend') {if(window.fixtureRecoverTo)window.fixtureConnection=window.fixtureRecoverTo;return true;}
                throw Error('Unexpected FFI method');
            },
            routerHook: {addRoute: (route, component) => window.fixtureRoutes.set(route, component), removeRoute: route => window.fixtureRoutes.delete(route)},
            Navigation: {Navigate: route => window.fixtureRoot.render(window.SP_REACT.createElement(window.fixtureRoutes.get(route)))},
            Millennium: {AddWindowCreateHook: callback => {window.fixtureHook = callback; callback({m_strTitle:'Steam Root Menu',window:window.fixturePopup.contentWindow});}}
        };
    });
    const plugin = path.join(project, 'ember/millennium/frontend.js');
    await page.addScriptTag({path: plugin});
    const menu = page.frameLocator('#menu-fixture');
    await check('Millennium adapter registers an independent route and preserves its menu entry',async()=>{
        assert(await page.evaluate(()=>window.fixtureRoutes.has('/ember')));
        await menu.locator('#ember-steam-menuitem').waitFor();
        assert.equal(await menu.locator('#millennium-menuitem').count(),1);
        assert.equal(await menu.locator('#ember-steam-menuitem').getAttribute('aria-disabled'),'false');
        assert.equal(await menu.locator('#ember-steam-menuitem').evaluate(node=>getComputedStyle(node).color),'rgb(220, 222, 223)');
    });
    await menu.locator('#ember-steam-menuitem').click();
    await page.locator('#route').getByText('Запуск Ember…',{exact:true}).waitFor();
    await page.locator('#menu-fixture').evaluate(node=>node.style.display='none');
    await check('Unavailable backend has a retry action inside Steam',async()=>{
        await page.evaluate(()=>window.fixtureConnection={error:'Ember остановлен. Повторите подключение.'});
        await page.getByText('Ember остановлен. Повторите подключение.',{exact:true}).waitFor();
        await page.getByRole('button',{name:'Подключиться повторно'}).click();
        assert((await page.evaluate(()=>window.fixtureCalls)).includes('start_backend'));
    });
    await check('Millennium reconnection screen follows the saved English language',async()=>{
        await page.evaluate(()=>window.fixtureConnection={language:'en',error:'Ember остановлен. Повторите подключение.'});
        await page.getByText('Ember has stopped. Try reconnecting.',{exact:true}).waitFor();
        await page.getByRole('button',{name:'Reconnect',exact:true}).click();
    });
    await page.evaluate(value=>window.fixtureConnection=value,info);
    const frame = page.frameLocator('#route > iframe');
    await frame.locator('.ember-status[data-connected=true]').waitFor({timeout:20000});
    await check('Embedded page fills only Steam content and matches the reference sidebar',async()=>{
        const host = await page.locator('#route').boundingBox();
        const embedded = await page.locator('#route > iframe').boundingBox();
        assert.deepEqual(embedded,host);
        assert.equal((await frame.locator('.sidebar').boundingBox()).width,220);
        assert.equal(await frame.locator('.sidebar-nav .nav-item[data-page]').count(),5);
        assert.equal(await frame.locator('.sidebar-nav .nav-item[data-page] .nav-icon svg').count(),5);
        assert.equal(await page.locator('header').count(),1);
        assert.equal(await page.locator('footer').count(),1);
        assert.equal(await page.locator('#ember-steam-panel').count(),0);
    });
    await page.screenshot({path:path.join(reportDir,'millennium-home.png')});
    await frame.locator('[data-page="ember-settings"]').click();
    await page.screenshot({path:path.join(reportDir,'millennium-settings.png')});
    await check('Reloading the adapter does not duplicate routes or menu entries',async()=>{
        await page.addScriptTag({path:plugin});
        assert.equal(await menu.locator('#ember-steam-menuitem').count(),1);
        assert.equal(await menu.locator('#millennium-menuitem').count(),1);
        assert.equal(await page.evaluate(()=>window.fixtureRoutes.size),1);
        await page.evaluate(()=>window.MILLENNIUM_API.Navigation.Navigate('/ember'));
        await frame.locator('.ember-status[data-connected=true]').waitFor({state:'attached'});
        assert.equal(await page.locator('#route > iframe').count(),1);
    });
    if(rpc && process.env.EMBER_ADAPTER_ONLY) await require('./check_store.cjs')({context,info,project,reportDir,check,rpc,hostPage:page,millennium:true});
    await check('A hung FFI status call cannot freeze polling or automatic recovery',async()=>{
        const before=await page.evaluate(()=>window.fixtureCalls.filter(value=>value==='start_backend').length);
        await page.evaluate(value=>{window.fixtureRecoverTo=value;window.fixtureConnection={starting:true};window.fixtureHangOnce=true;},info);
        await page.waitForFunction(before=>window.fixtureCalls.filter(value=>value==='start_backend').length>before,before,{timeout:20000});
        await frame.locator('.ember-status[data-connected=true]').waitFor({timeout:15000});
        assert.equal(await page.locator('#route > iframe').count(),1);
    });
    await check('Removing the adapter restores the original menu and removes its route',async()=>{
        await page.evaluate(()=>window.__emberMillennium.dispose());
        assert.equal(await menu.locator('#ember-steam-menuitem').count(),0);
        assert.equal(await menu.locator('#millennium-menuitem').count(),1);
        assert.equal(await page.evaluate(()=>window.fixtureRoutes.size),0);
        assert.deepEqual(errors,[]);
    });
    await page.close();
};
