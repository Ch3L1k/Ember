/* Ember — Copyright (C) 2026 Ember contributors.
 * GNU GPL version 3 or later; distributed without any warranty.
 * See LICENSE for the full license and warranty disclaimer.
 */
const assert=require('node:assert/strict');
const path=require('node:path');
module.exports=async function({context,info,reportDir,check,rpc}){
 let state=JSON.parse((await rpc('ember_get_workspace')).result);
 for(const game of state.pins)await rpc('ember_update_workspace',[JSON.stringify({action:'toggle_pin',game})]);
 for(const action of ['clear_searches','clear_recent'])await rpc('ember_update_workspace',[JSON.stringify({action})]);
 const page=await context.newPage();const errors=[];page.on('pageerror',error=>errors.push(error.message));
 await page.goto(info.origin+'/?surface=steam#token='+encodeURIComponent(info.token));
 await page.waitForFunction(()=>window.EmberCatalog?.workspace.revision>=0);
 const pin=()=>page.locator('#store-grid .game-card[data-appid="900000002"] .ember-pin');
 await pin().waitFor();
 await check('Catalog has a compact start screen, keyboard search and recent queries',async()=>{
  assert.equal(await page.locator('.ember-catalog-tab').count(),3);
  await page.evaluate(()=>App.navigateTo('ember-tools'));
  await page.keyboard.press('Control+k');
  assert(await page.locator('#store-search').evaluate(node=>node===document.activeElement));
  await page.locator('#store-search').fill('Ember');await page.keyboard.press('Enter');
  await page.locator('.ember-search-chip').getByText('Ember',{exact:true}).waitFor();
 });
 await check('Saved games are separate from Steam ownership and survive page reload',async()=>{
  await pin().click();await page.waitForFunction(()=>window.EmberCatalog.workspace.pins.length===1);
  await page.locator('.ember-catalog-tab[data-view=pins]').click();
  await page.locator('#ember-saved-content .game-card-name').getByText('Ember Puzzle',{exact:true}).waitFor();
  assert.equal(await page.locator('#store-grid').isVisible(),false);
  await page.reload();await page.waitForFunction(()=>window.EmberCatalog?.workspace.pins.length===1);
  await pin().waitFor();assert.equal(await pin().getAttribute('aria-pressed'),'true');
  assert.equal(await page.locator('.ember-search-chip').first().innerText(),'Ember');
 });
 await check('Removing a saved game updates both catalog and empty saved view',async()=>{
  await page.locator('.ember-catalog-tab[data-view=pins]').click();
  await page.locator('#ember-saved-content .ember-pin').click();
  await page.locator('.ember-saved-empty h2').getByText('Игры на потом',{exact:true}).waitFor();
  assert.equal(await page.locator('#ember-saved-content .game-card').count(),0);
 });
 await check('Persistent activity records actual terminal results and searches by App ID',async()=>{
  await rpc('ember_lab_add_game',[JSON.stringify({name:'task_finished',data:{task:'download_fastest',app_id:'900000002',name:'Ember Puzzle',success:true}})]);
  await page.locator('.ember-catalog-tab[data-view=recent]').click();
  await page.locator('.ember-activity-row').getByText('Ember Puzzle',{exact:true}).waitFor();
  await page.locator('.ember-activity-row').getByText('Данные переданы Steam',{exact:true}).waitFor();
  await page.getByRole('button',{name:'Найти в каталоге',exact:true}).click();
  await page.locator('#store-grid .game-card[data-appid="900000002"]').waitFor();
  assert.equal(await page.locator('#store-search').inputValue(),'900000002');
  assert.equal(await page.getByText('Download completed. The game is in your library.',{exact:true}).count(),0);
  await page.waitForFunction(()=>Number(getComputedStyle(document.querySelector('#store-grid .game-card')).opacity)===1);
  await page.screenshot({path:path.join(reportDir,'catalog-start.png')});
  await page.locator('.ember-catalog-tab[data-view=recent]').click();
  await page.screenshot({path:path.join(reportDir,'catalog-activity.png')});
 });
 await check('Activity and search history can be cleared without altering game files',async()=>{
  await page.getByRole('button',{name:'Очистить историю',exact:true}).click();
  await page.locator('.ember-saved-empty h2').getByText('Здесь будут результаты добавлений',{exact:true}).waitFor();
  await page.getByRole('button',{name:'Очистить историю поиска',exact:true}).click();
  await page.waitForFunction(()=>window.EmberCatalog.workspace.searches.length===0);
  assert.equal(await page.locator('.ember-search-chip').count(),0);
  assert.deepEqual(errors,[]);
 });
 await page.close();
};
