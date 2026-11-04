/* Ember — Copyright (C) 2026 Ember contributors.
 * GNU GPL version 3 or later; distributed without any warranty.
 * See LICENSE for the full license and warranty disclaimer.
 */
const assert=require('node:assert/strict'),path=require('node:path');
module.exports=async function({context,info,reportDir,check,rpc}){
 const page=await context.newPage(),errors=[],calls=[];let reject=false;
 page.on('pageerror',error=>errors.push(error.message));
 await page.goto(info.origin+'/?surface=steam#token='+encodeURIComponent(info.token));
 await page.locator('#store-grid .game-card').first().waitFor();
 await page.route(info.origin+'/api/call',route=>{
  const body=route.request().postDataJSON();if(body.method!=='search_games')return route.continue();
  calls.push(body.args);return route.fulfill({status:reject?503:200,json:reject?{error:'Fixture search unavailable'}:{result:null}});
 });
 const query=async value=>{await page.locator('#store-search').fill(value);await page.locator('#store-search-btn').click();};
 const result=(request,name)=>rpc('ember_lab_add_game',[JSON.stringify({name:'search_results',data:{request_id:request[5],games:[{app_id:'900000002',name,image_url:'/ember/mark.svg'}],total:1}})]);
 await check('Search immediately shows Steam-style activity, elapsed time and a busy button',async()=>{
  await query('Fixture A');await page.locator('#ember-search-status[data-busy=true]').waitFor();
  assert.equal(await page.locator('#store-search-btn').innerText(),'Ищем…');
  assert.equal(await page.locator('#page-store').getAttribute('aria-busy'),'true');
  assert.equal(await page.locator('#store-search-btn').isDisabled(),false);
  await page.screenshot({path:path.join(reportDir,'search-pending.png')});
 });
 await check('Duplicate searches are ignored and old replies cannot stop the latest search',async()=>{
  await page.waitForFunction(()=>Store.getSearchState().requestId!=='');
  const old=calls[0];await page.locator('#store-search-btn').click();assert.equal(calls.length,1);
  await query('Fixture B');await page.waitForFunction(id=>Store.getSearchState().requestId!==id,old[5]);
  const latest=calls.at(-1);await result(old,'Stale fixture');
  assert.equal(await page.locator('#page-store').getAttribute('aria-busy'),'true');
  await result(latest,'Current fixture');await page.locator('#store-grid').getByText('Current fixture',{exact:true}).waitFor();
  assert.equal(await page.locator('#ember-search-status').isVisible(),false);
  assert.equal(await page.locator('#store-search-btn').innerText(),'Найти');
 });
 await check('A cached query remains visible after a late response from an older request',async()=>{
  await query('Fixture C');const old=calls.at(-1);await query('Fixture B');
  await page.locator('#store-grid').getByText('Current fixture',{exact:true}).waitFor();
  await result(old,'Late fixture');assert.equal(await page.locator('#store-grid').innerText().then(text=>text.includes('Late fixture')),false);
  assert.equal(await page.locator('#ember-search-status').isVisible(),false);
 });
 await check('Background catalog enrichment updates only the current query',async()=>{
  await query('Fixture enrichment');
  const current=calls.at(-1);
  await result(current,'Local fixture');
  await page.locator('#store-grid').getByText('Local fixture',{exact:true}).waitFor();
  const enrich=(request,name)=>rpc('ember_lab_add_game',[JSON.stringify({name:'task_finished',data:{task:'ember_search_enrichment',app_id:'900000002',request_id:request[5],games:[{app_id:'900000002',name,image_url:'/ember/mark.svg'}],total:1}})]);
  await enrich(current,'Enriched fixture');
  await page.locator('#store-grid').getByText('Enriched fixture',{exact:true}).waitFor();
  await query('Fixture newer');const newer=calls.at(-1);
  await result(newer,'Newer fixture');
  await page.locator('#store-grid').getByText('Newer fixture',{exact:true}).waitFor();
  await enrich(current,'Obsolete enrichment');
  assert.equal(await page.locator('#store-grid').innerText().then(text=>text.includes('Obsolete enrichment')),false);
 });
 await check('Search failure clears activity and an English retry can search again',async()=>{
  reject=true;await query('Fixture failure');
  await page.locator('#ember-search-status[data-error=true]').waitFor();
  assert.equal(await page.locator('#page-store').getAttribute('aria-busy'),'false');
  await rpc('ember_set_language',['en']);await page.getByText('Search did not complete. Please try again.',{exact:true}).waitFor();
  reject=false;await query('Fixture English');await page.locator('#store-search-btn').getByText('Searching…',{exact:true}).waitFor();
  await result(calls.at(-1),'English fixture');await page.locator('#ember-search-status').waitFor({state:'hidden'});
  assert.equal(await page.locator('#store-search-btn').innerText(),'Search');
  assert.deepEqual(errors,[]);await rpc('ember_set_language',['ru']);
 });
 await page.close();
};
