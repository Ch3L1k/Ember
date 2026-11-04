/* Ember — Copyright (C) 2026 Ember contributors.
 * GNU GPL version 3 or later; distributed without any warranty.
 * See LICENSE for the full license and warranty disclaimer.
 */
const assert=require('node:assert/strict');
const path=require('node:path');
module.exports=async function({context,info,reportDir,check,rpc}){
 const page=await context.newPage();
 const errors=[],urls=[];page.on('pageerror',error=>errors.push(error.message));
 let installed=false,toolCalls=0,searches=0;
 page.on('request',request=>{if(request.url().endsWith('/api/call')&&request.postDataJSON()?.method==='search_games')searches++;});
 await page.route(info.origin+'/api/call',async route=>{
  const body=route.request().postDataJSON();
  if(body.method==='open_url'){urls.push(body.args[0]);return route.fulfill({json:{result:null}});}
  if(body.method!=='ember_tool_action')return route.continue();
  toolCalls++;const [id,action]=body.args;
  if(['diagnose','repair_launch'].includes(action)) {
   await route.fulfill({json:{result:null}});
   await rpc('ember_lab_add_game',[JSON.stringify({name:'task_finished',data:{task:'ember_tool',app_id:id,action,success:true,repairable:action==='diagnose',checks:['Fixture prefix check'],message:action==='diagnose'?'NTFS prefix':'Prefix copied',backup:action==='repair_launch'?'/fixture/backup':null}})]);
   return;
  }
  if(action==='dlc_install')installed=true;
  if(action==='dlc_remove')installed=false;
  await route.fulfill({json:{result:null}});
  await rpc('ember_lab_add_game',[JSON.stringify({name:'task_finished',data:{task:'ember_tool',app_id:id,action,success:true,supported:true,installed,conflict:false,api_files:1,restore_files:installed?1:0,can_restore:installed}})]);
 });
 await page.goto(info.origin+'/?surface=steam#token='+encodeURIComponent(info.token));
 await page.waitForFunction(()=>Bridge.isReady()&&!!document.getElementById('ember-tool-game'));
 await page.evaluate(()=>App.navigateTo('ember-tools'));
 await page.locator('#ember-tool-game option[value="900000001"]').waitFor({state:'attached'});
 await check('DLC tools inspect only the selected game and restore button states after completion',async()=>{
  assert.equal(toolCalls,0);
  await page.locator('#ember-tool-game').selectOption('900000001');
  await page.waitForFunction(()=>!document.getElementById('ember-dlc-install').disabled);
  await page.locator('#ember-dlc-install').click();
  await page.waitForFunction(()=>!document.getElementById('ember-dlc-remove').disabled);
  assert(await page.locator('#ember-dlc-install').isDisabled());
  await page.screenshot({path:path.join(reportDir,'tools-dlc.png')});
  await page.locator('#ember-dlc-remove').click();
  await page.waitForFunction(()=>!document.getElementById('ember-dlc-install').disabled);
  assert(await page.locator('#ember-dlc-remove').isDisabled());
 });
 await check('Launch diagnostics require a completed check before repair',async()=>{
  await page.locator('#ember-diagnose').waitFor();
  assert(await page.locator('#ember-repair-launch').isDisabled());
  await page.locator('#ember-diagnose').click();
  await page.waitForFunction(()=>!document.getElementById('ember-repair-launch').disabled);
  assert((await page.locator('#ember-diagnostic-report').innerText()).includes('NTFS prefix'));
  await page.locator('#ember-repair-launch').click();
  await page.waitForFunction(()=>document.getElementById('ember-diagnostic-report').textContent.includes('/fixture/backup'));
  assert(await page.locator('#ember-repair-launch').isDisabled());
  await page.screenshot({path:path.join(reportDir,'launch-diagnostics.png')});
 });
 await check('Linux DLC information names the actual backend without claiming DLL changes',async()=>{
  await rpc('ember_lab_add_game',[JSON.stringify({name:'task_finished',data:{task:'ember_tool',app_id:'900000001',action:'inspect',success:true,backend:'sls',supported:true,installed:false,can_restore:false}})]);
  await page.locator('#ember-component-facts').getByText('Компонент: SLSsteam',{exact:true}).waitFor();
  assert(!(await page.locator('#ember-component-facts').innerText()).includes('SmokeAPI'));
  assert((await page.locator('#ember-dlc-description').innerText()).includes('Файлы игры не заменяются'));
  assert.equal(await page.locator('#ember-dlc-remove').innerText(),'Выключить');
 });
 await check('Tools omits duplicate Steam settings and file verification controls',async()=>{
  assert.equal(await page.locator('#ember-tool-properties,#ember-tool-validate').count(),0);
  assert.equal(await page.locator('#page-ember-tools .ember-tool-panel').count(),2);
  assert.deepEqual(urls,[]);
 });
 await page.evaluate(()=>App.navigateTo('store'));
 await page.locator('#store-grid .game-card').first().waitFor();
 await check('Repeated navigation keeps catalog nodes and sends no repeated search requests',async()=>{
  const before=searches;
  await page.evaluate(()=>window.fixtureCard=document.querySelector('#store-grid .game-card'));
  const elapsed=await page.evaluate(async()=>{
   const start=performance.now();
   for(let i=0;i<20;i++){
    App.navigateTo('ember-tools');await new Promise(requestAnimationFrame);
    App.navigateTo('store');await new Promise(requestAnimationFrame);
   }
   return performance.now()-start;
  });
  assert(await page.evaluate(()=>window.fixtureCard===document.querySelector('#store-grid .game-card')));
  assert.equal(searches,before);
  require('node:fs').writeFileSync(path.join(reportDir,'performance.json'),JSON.stringify({navigation_cycles:20,catalog_node_preserved:true,additional_search_requests:searches-before,elapsed_ms:elapsed,environment:'isolated headless Chromium fixture'},null,2));
 });
 await check('Tools frontend has no unhandled JavaScript errors',async()=>assert.deepEqual(errors,[]));
 await page.close();
};
