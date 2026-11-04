/* Ember — Copyright (C) 2026 Ember contributors.
 * GNU GPL version 3 or later; distributed without any warranty.
 * See LICENSE for the full license and warranty disclaimer.
 */
const assert=require('node:assert/strict');
const path=require('node:path');
module.exports=async function({context,info,reportDir,check,rpc}){
 const page=await context.newPage();const errors=[],toolCalls=[];let refreshes=0;
 page.on('pageerror',error=>errors.push(error.message));
 page.on('request',request=>{if(request.url().endsWith('/api/call')&&request.postDataJSON()?.method==='ember_library_refresh')refreshes++;});
 await page.route(info.origin+'/api/call',async route=>{
  const data=route.request().postDataJSON();
  if(data.method==='ember_tool_action'){
   toolCalls.push(data.args);await route.fulfill({json:{result:null}});
   await rpc('ember_lab_add_game',[JSON.stringify({name:'task_finished',data:{task:'ember_tool',app_id:data.args[0],action:data.args[1],success:true,supported:true,installed:true,restore_files:1,can_restore:true}})]);return;
  }
  await route.continue();
 });
 await page.goto(info.origin+'/?surface=steam#token='+encodeURIComponent(info.token));
 await page.waitForFunction(()=>Bridge.isReady()&&!!document.getElementById('ember-library-list'));
 await page.locator('[data-page=ember-library]').click();
 const row=id=>page.locator('.ember-library-game[data-appid="'+id+'"]');
 await check('Management library includes registered games before installation with per-game Steam actions',async()=>{
  await row('900000002').waitFor();
  await row('900000002').getByRole('button',{name:'Скачать',exact:true}).waitFor();
  assert(await row('900000002').getByRole('button',{name:'Установить DLC',exact:true}).isDisabled());
  await row('900000001').getByRole('button',{name:'Играть',exact:true}).waitFor();
  await row('900000001').getByRole('button',{name:'Папка игры',exact:true}).waitFor();
  await page.screenshot({path:path.join(reportDir,'management-library.png')});
 });
 await check('Library search and filters do not issue backend scans on every change',async()=>{
  const count=refreshes;await page.locator('#ember-library-search').fill('900000002');
  await row('900000001').waitFor({state:'detached'});assert.equal(await page.locator('.ember-library-game').count(),1);
  await page.locator('#ember-library-search').fill('');await page.locator('#ember-library-filter').selectOption('installed');
  await row('900000001').waitFor();assert.equal(await page.locator('.ember-library-game').count(),1);
  assert.equal(refreshes,count);await page.locator('#ember-library-filter').selectOption('all');
 });
 await check('Removing an Ember registration requires confirmation and offers undo without deleting the installed game',async()=>{
  await row('900000001').getByRole('button',{name:'Удалить из Ember',exact:true}).click();
  await page.locator('#confirm-dialog-message').getByText(/Файлы игры и сохранения останутся/).waitFor();
  await page.locator('#confirm-dialog-no').click();assert.equal(await row('900000001').count(),1);
  await row('900000001').getByRole('button',{name:'Удалить из Ember',exact:true}).click();await page.locator('#confirm-dialog-yes').click();
  await row('900000001').waitFor({state:'detached'});
  const installed=JSON.parse((await rpc('get_installed_games')).result);assert(installed.some(game=>String(game.app_id)==='900000001'));
  await page.getByRole('button',{name:'Отменить удаление',exact:true}).click();
  await row('900000001').getByRole('button',{name:'Удалить из Ember',exact:true}).waitFor();
 });
 await check('Removed registrations remain restorable in their own filter after page reload',async()=>{
  await row('900000002').getByRole('button',{name:'Удалить из Ember',exact:true}).click();await page.locator('#confirm-dialog-yes').click();
  await row('900000002').waitFor({state:'detached'});
  await page.reload();await page.waitForFunction(()=>Bridge.isReady()&&!!document.getElementById('ember-library-list'));
  await page.locator('[data-page=ember-library]').click();await page.locator('#ember-library-filter').selectOption('removed');
  await row('900000002').getByRole('button',{name:'Восстановить',exact:true}).click();
  await row('900000002').waitFor({state:'detached'});
  await page.locator('#ember-library-filter').selectOption('all');await row('900000002').waitFor();
 });
 await check('Download commands stay inside the fixture and DLC actions select the exact installed game',async()=>{
  await row('900000002').getByRole('button',{name:'Скачать',exact:true}).click();
  await page.locator('#ember-library-status').getByText('Тестовая среда: запуск Steam и открытие папок отключены.',{exact:true}).waitFor();
  await row('900000001').getByRole('button',{name:'Установить DLC',exact:true}).click();
  await page.locator('#page-ember-tools.active').waitFor();
  await page.waitForFunction(()=>!document.getElementById('ember-dlc-remove').disabled);
  assert.deepEqual(toolCalls.at(-1),['900000001','dlc_install']);
 });
 await check('Library supports English without translating game names',async()=>{
  await page.locator('[data-page=ember-settings]').click();await page.locator('#ember-language').selectOption('en');
  await page.waitForFunction(()=>document.documentElement.lang==='en');await page.locator('[data-page=ember-library]').click();
  await row('900000002').getByRole('button',{name:'Download',exact:true}).waitFor();
  assert.equal(await row('900000002').locator('strong').innerText(),'Ember Puzzle');
  assert.doesNotMatch(await page.locator('#page-ember-library').innerText(),/[А-Яа-я]/);
  assert.deepEqual(errors,[]);await page.screenshot({path:path.join(reportDir,'management-library-en.png')});
 });
 await rpc('ember_set_language',['ru']);await page.close();
};
