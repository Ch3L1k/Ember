/* Ember — Copyright (C) 2026 Ember contributors.
 * GNU GPL version 3 or later; distributed without any warranty.
 * See LICENSE for the full license and warranty disclaimer.
 */
const assert=require('node:assert/strict');
const path=require('node:path');
module.exports=async function({context,info,project,reportDir,check,rpc}){
 const page=await context.newPage();
 const errors=[];page.on('pageerror',error=>errors.push(error.message));
 let calls=0,reject=false;
 await page.route(info.origin+'/api/call',async route=>{
  const body=route.request().postDataJSON();
  if(body.method!=='download_game_with_source')return route.continue();
  calls++;
  await route.fulfill({status:reject?503:200,json:reject?{error:'Тест: источник недоступен'}:{result:null}});
 });
 await page.goto(info.origin+'/?surface=steam#token='+encodeURIComponent(info.token));
 await page.waitForFunction(()=>!!window.EmberAdditions && Bridge.isReady());
 await page.evaluate(()=>App.navigateTo('store'));
 const id='900000003';
 const button=page.locator('.btn-download[data-appid="'+id+'"]');
 await button.waitFor();
 await page.setViewportSize({width:850,height:724});
 await check('Add dialog keeps its primary action visible and advanced controls collapsed',async()=>{
  await page.evaluate(()=>Components.showDownloadModal('900000003','Ember Racing','win32'));
  await page.waitForFunction(()=>getComputedStyle(document.querySelector('#download-modal .modal-content')).opacity==='1'&&getComputedStyle(document.getElementById('download-modal')).opacity==='1');
  assert(await page.locator('#dl-fastest').isVisible());
  assert(await page.locator('#dl-ddmod').isHidden());
  assert(await page.locator('#dl-ddmod-dest-path').isHidden());
  await page.screenshot({path:path.join(reportDir,'add-dialog.png')});
  await page.locator('.ember-add-settings>summary').click();
  await page.locator('#ember-add-source').selectOption('local');
  assert(await page.locator('#dl-local-row').isVisible());
  await page.locator('#dl-fastest').click();
  assert(await page.locator('#download-modal').isVisible());
  assert(await page.locator('.ember-add-local-warning').isVisible());
  assert.equal(calls,0);
  await page.locator('#ember-add-source').selectOption('freelua');
  assert(await page.locator('#dl-local-row').isHidden());
  await page.locator('.ember-add-alternatives>summary').click();
  assert(await page.locator('#dl-ddmod').isVisible());
  await page.screenshot({path:path.join(reportDir,'add-dialog-options.png')});
  await page.setViewportSize({width:390,height:580});
  const fit=await page.locator('#download-modal .modal-content').evaluate(node=>{
   const rect=node.getBoundingClientRect(),button=document.getElementById('dl-fastest').getBoundingClientRect();
   return {overflow:node.scrollWidth>node.clientWidth,inside:rect.top>=0&&rect.bottom<=innerHeight&&button.bottom<=innerHeight};
  });
  assert(!fit.overflow);assert(fit.inside);
  await page.screenshot({path:path.join(reportDir,'add-dialog-narrow.png')});
  await page.locator('#download-modal .modal-cancel').click();
  await page.locator('#download-modal').waitFor({state:'hidden'});
  await page.setViewportSize({width:850,height:724});
 });
 const call=()=>page.evaluate(id=>Bridge.call('download_game_with_source',id,'','0'),id);
 const emit=(name,data)=>rpc('ember_lab_add_game',[JSON.stringify({name,data})]);
 await check('Catalog add action immediately shows a spinner and rejects duplicate submissions',async()=>{
  assert.equal(await button.innerText(),'Добавить');
  await call();
  await page.locator('#ember-add-status [data-state=pending]').waitFor();
  assert.equal(await button.getAttribute('aria-busy'),'true');
  assert(await button.isDisabled());
  assert.equal(await page.locator('.ember-add-spinner').count(),1);
  assert.equal(await page.getByRole('progressbar').getAttribute('aria-valuenow'),'0');
  await page.locator('.ember-add-phase').getByText('Этап 1 из 4',{exact:true}).waitFor();
  await call();await new Promise(resolve=>setTimeout(resolve,200));assert.equal(calls,1);
 });
 await check('Adding shows backend stages and survives navigation',async()=>{
  emit('download_progress',{app_id:id,status:'Installing Lua to Steam',progress:0});
  await page.getByRole('status').getByText('Передача данных Steam…',{exact:true}).waitFor();
  assert.equal(await page.getByRole('progressbar').getAttribute('aria-valuenow'),'2');
  assert.equal(await page.locator('.ember-add-progress-active').count(),1);
  await page.evaluate(()=>window.dispatchEvent(new CustomEvent('ember:connection',{detail:{connected:false}})));
  await page.locator('.ember-add-operation[data-waiting=true]').waitFor();
  await page.evaluate(()=>window.dispatchEvent(new CustomEvent('ember:connection',{detail:{connected:true}})));
  await page.evaluate(()=>App.navigateTo('ember-tools'));
  await emit('download_progress',{app_id:id,status:'Installing Lua to Steam',progress:0});
  await page.waitForFunction(()=>document.querySelector('.ember-add-detail').hidden&&getComputedStyle(document.getElementById('page-ember-tools')).opacity==='1');
  await page.locator('#ember-add-status [data-state=pending]').waitFor();
  await page.screenshot({path:path.join(reportDir,'adding-game.png')});
  await page.setViewportSize({width:390,height:580});
  const aligned=await page.locator('.ember-add-operation').evaluate(node=>{
   const footer=node.querySelector('.ember-add-footer').getBoundingClientRect(),bar=node.querySelector('.ember-add-progress').getBoundingClientRect();
   return node.scrollWidth===node.clientWidth&&footer.top>=bar.bottom&&node.getBoundingClientRect().right<=innerWidth;
  });
  assert(aligned);await page.screenshot({path:path.join(reportDir,'adding-game-narrow.png')});
  await page.setViewportSize({width:850,height:724});
 });
 await check('Completion explains Steam application without falsely confirming library presence',async()=>{
  emit('task_finished',{task:'download_fastest',app_id:id,success:true,message:'Download completed'});
  await page.locator('#ember-add-status [data-state=done]').waitFor();
  assert.equal(await page.getByRole('progressbar').getAttribute('aria-valuenow'),'4');
  assert.equal(await page.locator('.ember-add-progress-active').count(),0);
  const text=await page.locator('#ember-add-status').innerText();
  assert.match(text,/без перезапуска/);assert.match(text,/подтверждения.*пока нет/);assert.match(text,/Для скачивания файлов/);
  await page.evaluate(()=>App.navigateTo('store'));
  await button.getByText('Добавлено',{exact:true}).waitFor();
  assert(!(await button.isDisabled()));
 });
 await check('Source failure restores the button and gives an explicit retry action',async()=>{
  await call();emit('task_finished',{task:'download_fastest',app_id:id,success:false,source_empty:true});
  await page.locator('#ember-add-status [data-state=error]').waitFor();
  await page.getByRole('button',{name:'Повторить',exact:true}).waitFor();
  assert.equal(await button.innerText(),'Добавить');assert(!(await button.isDisabled()));
  assert.equal(await page.locator('.ember-add-progress-active').count(),0);
 });
 await check('RPC rejection cannot leave the add action spinning indefinitely',async()=>{
  reject=true;await call();
  await page.locator('#ember-add-status [data-state=error]').getByText('Тест: источник недоступен',{exact:true}).waitFor();
  assert(!(await button.isDisabled()));assert.equal(await page.locator('.ember-add-spinner').count(),0);
  assert.deepEqual(errors,[]);
 });
 await page.close();
};
