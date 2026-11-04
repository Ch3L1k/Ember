/* Ember — Copyright (C) 2026 Ember contributors.
 * GNU GPL version 3 or later; distributed without any warranty.
 * See LICENSE for the full license and warranty disclaimer.
 */
const assert=require('node:assert/strict'),path=require('node:path');
module.exports=async function({context,info,reportDir,check,rpc}){
 const page=await context.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
 await rpc('ember_set_language',['ru']);
 await page.goto(info.origin+'/?surface=steam#token='+encodeURIComponent(info.token));
 await page.waitForFunction(()=>window.EmberCatalog?.workspace.revision>=0&&document.documentElement.lang==='ru');
 const navigate=route=>page.evaluate(route=>App.navigateTo(route),route);
 const change=async language=>{
  await navigate('ember-settings');await page.locator('#ember-language').selectOption(language);
  await page.waitForFunction(language=>document.documentElement.lang===language&&!document.getElementById('ember-language').disabled,language);
 };
 await check('English applies live to navigation, settings and the revised Ch3L1k About page',async()=>{
  await change('en');
  assert.equal(await page.locator('.nav-item[data-page=store] .nav-label').innerText(),'Catalog');
  assert.equal(await page.locator('label[for=ember-language]').innerText(),'Interface language');
  await navigate('ember-about');
  const about=page.locator('#page-ember-about');
  assert.match(await about.innerText(),/Ember developer\s+Ch3L1k/);
  assert.match(await about.innerText(),/Upstream and license/);
  assert.doesNotMatch(await about.innerText(),/[А-Яа-я]/);
  assert.doesNotMatch(await about.innerText(),/local API|not implemented|не реализованы/);
  await page.waitForFunction(()=>getComputedStyle(document.getElementById('page-ember-about')).opacity==='1');
  await page.screenshot({path:path.join(reportDir,'about-en.png')});
 });
 await check('Language persists on reload and catalog history keeps original search text',async()=>{
  assert.equal((await rpc('get_setting',['language'])).result,'en');
  await page.reload();await page.waitForFunction(()=>document.documentElement.lang==='en'&&!!window.EmberCatalog);
  assert.equal(await page.locator('#ember-language').inputValue(),'en');
  await rpc('ember_update_workspace',[JSON.stringify({action:'remember_search',query:'Настройки'})]);
  await navigate('store');await page.locator('.ember-search-chip').getByText('Настройки',{exact:true}).waitFor();
  await page.locator('.game-card-name').first().waitFor();
  assert.equal(await page.locator('#store-search').getAttribute('placeholder'),'Game name or App ID');
  await page.evaluate(()=>document.querySelector('.game-card-name').textContent='Настройки');
  await change('ru');await change('en');await navigate('store');
  assert.equal(await page.locator('.game-card-name').first().innerText(),'Настройки');
  await page.locator('.ember-search-chip').getByText('Настройки',{exact:true}).waitFor();
  await page.screenshot({path:path.join(reportDir,'catalog-en.png')});
 });
 await check('English DLC states, progress, elapsed time and retry messages remain translated',async()=>{
  await page.route(info.origin+'/api/call',async route=>{
   const body=route.request().postDataJSON();
   if(body.method==='ember_tool_action'){
    await route.fulfill({json:{result:null}});
    await rpc('ember_lab_add_game',[JSON.stringify({name:'task_finished',data:{task:'ember_tool',app_id:body.args[0],success:true,supported:true,installed:false,api_files:2,restore_files:0,can_restore:false}})]);return;
   }
   if(body.method==='download_game_with_source')return route.fulfill({json:{result:null}});
   await route.continue();
  });
  await navigate('ember-tools');await page.locator('#ember-tool-game').selectOption('900000001');
  await page.getByText('Steam API found. SmokeAPI can be enabled.',{exact:true}).waitFor();
  await page.getByText('Steam API: 2',{exact:true}).waitFor();
  assert.doesNotMatch(await page.locator('#page-ember-tools').innerText(),/[А-Яа-я]/);
  await page.waitForFunction(()=>getComputedStyle(document.getElementById('page-ember-tools')).opacity==='1');
  await page.screenshot({path:path.join(reportDir,'tools-en.png')});
  await navigate('store');await page.evaluate(()=>Components.showDownloadModal('900000003','Ember Racing','windows'));
  assert.equal(await page.locator('#download-modal-title').innerText(),'Add: Ember Racing');
  assert.equal(await page.locator('#dl-fastest-title').innerText(),'Add to Steam');
  await page.evaluate(()=>Bridge.call('download_game_with_source','900000003','','0'));
  await page.locator('#ember-add-status').getByText('Starting addition…',{exact:true}).waitFor();
  assert.match(await page.locator('.ember-add-elapsed').innerText(),/^\d+ s$/);
  await rpc('ember_lab_add_game',[JSON.stringify({name:'download_progress',data:{app_id:'900000003',status:'Installing Lua to Steam',progress:0}})]);
  await page.locator('#ember-add-status').getByText('Sending data to Steam…',{exact:true}).waitFor();
  await rpc('ember_lab_add_game',[JSON.stringify({name:'task_finished',data:{task:'download_fastest',app_id:'900000003',success:false,source_empty:true}})]);
  await page.locator('#ember-add-status').getByRole('button',{name:'Retry',exact:true}).waitFor();
  assert.doesNotMatch(await page.locator('#ember-add-status').innerText(),/[А-Яа-я]/);
 });
 await check('Switching back restores Russian and rejects unsupported language values',async()=>{
  await rpc('ember_set_language',['ru']);
  await page.waitForFunction(()=>document.documentElement.lang==='ru');
  assert.equal(await page.locator('#download-modal-title').innerText(),'Добавить: Ember Racing');
  assert.equal(await page.locator('#dl-fastest-title').innerText(),'Добавить в Steam');
  await page.evaluate(()=>Components.hideModal('download-modal'));
  await page.locator('#download-modal').waitFor({state:'hidden'});
  await page.locator('#ember-add-status').getByRole('button',{name:'Понятно',exact:true}).click();
  await change('ru');await navigate('ember-about');
  assert.equal(await page.locator('#page-ember-about h1').innerText(),'Об Ember');
  assert.match(await page.locator('#page-ember-about').innerText(),/Разработчик Ember\s+Ch3L1k/);
  assert.match(await page.locator('#page-ember-about').innerText(),/Основа и лицензия/);
  assert.equal(await page.locator('#ember-language').inputValue(),'ru');
  const invalid=await rpc('ember_set_language',['invalid']);assert.equal(invalid.status,400);
  assert.equal((await rpc('get_setting',['language'])).result,'ru');
  assert.deepEqual(errors,[]);
  await page.waitForFunction(()=>getComputedStyle(document.getElementById('page-ember-about')).opacity==='1');
  await page.screenshot({path:path.join(reportDir,'about-ru.png')});
 });
 await page.close();
};
