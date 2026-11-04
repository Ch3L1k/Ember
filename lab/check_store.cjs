/* Ember — Copyright (C) 2026 Ember contributors.
 * GNU GPL version 3 or later; distributed without any warranty.
 * See LICENSE for the full license and warranty disclaimer.
 */
const assert=require('node:assert/strict');
const path=require('node:path');
const https=require('node:http');
function call(info,method,payload){
 const url=info.origin+'/api/store-add'+(method==='get_store_add_status'?'?request_id='+encodeURIComponent(payload[0]):'');
 const body=method==='request_store_add'?JSON.stringify({action:'request',app_id:payload[0],name:payload[1]}):null;
 return new Promise((resolve,reject)=>{
  const request=https.request(url,{method:body?'POST':'GET',headers:{Authorization:'Bearer '+info.token,'Content-Type':'application/json',...(body?{'Content-Length':Buffer.byteLength(body)}:{})}},response=>{
   let raw='';response.on('data',chunk=>raw+=chunk);response.on('end',()=>{try{resolve(JSON.parse(raw));}catch(error){reject(error);}});
  });request.on('error',reject);if(body)request.write(body);request.end();
 });
}
module.exports=async function({context,info,project,reportDir,check,rpc,hostPage,millennium=false,embedFrame=null,label=null}){
 const mode=label||(millennium?'Millennium':'Standalone');
 const store=await context.newPage();const errors=[],ffiLog=[];store.on('pageerror',error=>errors.push(error.message));
 const id='900000002',name='Ember Store Demo';let additions=[];
 await hostPage.route(info.origin+'/api/call',route=>{
  const body=route.request().postDataJSON();
  if(body.method==='get_game_platforms')return route.fulfill({json:{result:'["windows"]'}});
  if(body.method==='get_crack_info')return route.fulfill({json:{result:'{"found":false}'}});
  if(body.method==='download_game_with_source'){additions.push(body.args);return route.fulfill({json:{result:null}});}
  return route.continue();
 });
 await store.route('https://store.steampowered.com/**',route=>route.fulfill({contentType:'text/html',body:`<!doctype html><html lang="ru"><meta charset="utf-8"><title>Ember store fixture</title><style>body{background:#1b2838;color:#c7d5e0;font:16px Arial;margin:0}header{background:#171d25;padding:28px}main{max-width:940px;margin:40px auto}#appHubAppName{font-size:28px;color:white;margin-bottom:25px}.art{height:280px;background:linear-gradient(125deg,#244252,#172231);display:grid;place-items:center;font-size:60px;color:#80a6bd;margin-bottom:24px}#game_area_purchase{padding:28px;background:#ffffff16}button{padding:10px 20px}</style><header>Steam　 МАГАЗИН　 БИБЛИОТЕКА　 СООБЩЕСТВО</header><main><div id="appHubAppName">Ember Store Demo</div><div class="art">EMBER LAB</div><div id="game_area_purchase"><h2>Купить Ember Store Demo</h2><button id="original-purchase">В корзину</button></div></main></html>`}));
 await store.goto('https://store.steampowered.com/app/'+id+'/Ember_Store_Demo/');
 if(millennium){
  await store.exposeFunction('fixtureStoreCall',async(method,args)=>{const value=await call(info,method,args);ffiLog.push({method,state:value.state,success:value.success});return value;});
  await store.evaluate(()=>window.MILLENNIUM_API={ffi:(_,method)=>(...args)=>window.fixtureStoreCall(method,args)});
  await store.addScriptTag({path:path.join(project,'ember/millennium/webkit.js')});
 }
 const button=store.locator('#ember-store-add');
 const frame=embedFrame||hostPage.frameLocator(millennium?'#route > iframe':'#ember-steam-panel iframe');
 await check(mode+' store page has one native-style add action without a local API token',async()=>{
  await button.waitFor({timeout:20000});assert.equal(await button.innerText(),'Добавить через Ember');
  assert.equal(await store.locator('#original-purchase').count(),1);
  assert.equal(await store.evaluate(()=>!!window.__EMBER_CONFIG__),false);
  assert.equal(await store.evaluate(()=>sessionStorage.getItem('ember-session-token')),null);
  assert.equal(await button.locator('svg circle,svg rect,svg defs').count(),0);
  assert.equal(await button.locator('svg path').getAttribute('fill'),'#fff');
  await store.screenshot({path:path.join(reportDir,'store-button-'+mode.toLowerCase()+'.png')});
 });
 await check(mode+' store button opens the correct source picker with visible feedback',async()=>{
  await button.click();assert.equal(await button.getAttribute('aria-busy'),'true');assert(await button.isDisabled());
  await frame.locator('#download-modal-title').getByText('Добавить: '+name,{exact:true}).waitFor({timeout:20000});
  assert.equal(await frame.locator('#dl-fastest').getAttribute('data-appid'),id);
  try{await button.getByText('Открыто в Ember',{exact:true}).waitFor({timeout:20000});}
  catch(error){console.log('Store diagnostics',JSON.stringify({button:await button.innerText(),ffiLog,methods:millennium?await hostPage.evaluate(()=>window.fixtureCalls):[]}));throw error;}
 });
 await check(mode+' store action uses the same add operation, name and real stage progress',async()=>{
  await frame.locator('#dl-fastest').click();
  await frame.locator('#ember-add-status [data-appid="'+id+'"][data-state=pending]').waitFor();
  assert.equal(additions.length,1);assert.equal(additions[0][0],id);
  assert.equal(await frame.locator('#ember-add-status strong').innerText(),name);
  await rpc('ember_lab_add_game',[JSON.stringify({name:'download_progress',data:{app_id:id,status:'Installing Lua to Steam'}})]);
  await frame.locator('#ember-add-status').getByText('Передача данных Steam…',{exact:true}).waitFor();
  await button.click();await button.getByText('Открыто в Ember',{exact:true}).waitFor({timeout:15000});
  assert.equal(additions.length,1);
  await rpc('ember_lab_add_game',[JSON.stringify({name:'task_finished',data:{task:'download_fastest',app_id:id,success:true}})]);
  await frame.locator('#ember-add-status [data-state=done]').waitFor();
 });
 await check(mode+' store button follows page changes and disappears outside valid app pages',async()=>{
  await store.evaluate(()=>{history.pushState({},'', '/app/900000003/Other/');document.getElementById('appHubAppName').textContent='Other game';});
  await store.locator('#ember-store-action[data-appid="900000003"]').waitFor();
  assert.equal(await store.locator('#ember-store-action').count(),1);
  await store.evaluate(()=>history.pushState({},'', '/sub/12/'));
  await store.locator('#ember-store-action').waitFor({state:'detached',timeout:5000});
  await store.evaluate(()=>history.pushState({},'', '/app/4294967296/Invalid/'));
  await new Promise(resolve=>setTimeout(resolve,1200));assert.equal(await button.count(),0);
  assert.deepEqual(errors,[]);
 });
 await check(mode+' store adapter reloads once and exposes a retry after a connection failure in English',async()=>{
  await store.evaluate(()=>{window.__emberStoreBinding=undefined;history.pushState({},'', '/app/900000003/Other/');document.documentElement.lang='en';window.MILLENNIUM_API={ffi:()=>async()=>{throw Error('Fixture connection failure');}};});
  await store.addScriptTag({path:path.join(project,'ember/millennium/webkit.js')});
  assert.equal(await button.count(),1);assert.equal(await store.locator('#ember-store-style').count(),1);
  assert.equal(await button.innerText(),'Add with Ember');await button.click();
  await button.getByText('Ember is not responding. Retry',{exact:true}).waitFor();assert(!(await button.isDisabled()));
 });
 await check(mode+' store button recovers a temporary startup failure without another click',async()=>{
  await store.evaluate(()=>{
   window.fixtureRecoveryRequests=0;
   window.MILLENNIUM_API={ffi:(_,method)=>async()=>{
    if(method==='request_store_add'){
     window.fixtureRecoveryRequests++;
     if(window.fixtureRecoveryRequests===1)throw Error('Fixture backend still starting');
     return {success:true,request_id:'recovered-request',language:'en'};
    }
    return {state:'opened',language:'en'};
   }};
  });
  await store.addScriptTag({path:path.join(project,'ember/millennium/webkit.js')});
  await button.click();
  await button.getByText('Reconnecting to Ember…',{exact:true}).waitFor();assert(await button.isDisabled());
  await button.getByText('Opened in Ember',{exact:true}).waitFor({timeout:10000});
  assert.equal(await store.evaluate(()=>window.fixtureRecoveryRequests),2);
  assert.equal(additions.length,1);
 });
 await check(mode+' store request survives a backend restart before the picker opens',async()=>{
  await store.evaluate(()=>{
   window.fixtureRecoveryRequests=0;
   window.MILLENNIUM_API={ffi:(_,method)=>async(request)=>{
    if(method==='request_store_add'){
     window.fixtureRecoveryRequests++;
     return {success:true,request_id:window.fixtureRecoveryRequests===1?'before-restart':'after-restart',language:'en'};
    }
    return {state:request==='before-restart'?'expired':'opened',language:'en'};
   }};
  });
  await store.addScriptTag({path:path.join(project,'ember/millennium/webkit.js')});
  await button.click();
  await button.getByText('Opened in Ember',{exact:true}).waitFor({timeout:10000});
  assert.equal(await store.evaluate(()=>window.fixtureRecoveryRequests),2);
  assert.equal(additions.length,1);
 });
 await hostPage.unroute(info.origin+'/api/call');
 await store.close();
};
