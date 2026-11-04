/* Ember — Copyright (C) 2026 Ember contributors.
 * GNU GPL version 3 or later; distributed without any warranty.
 * See LICENSE for the full license and warranty disclaimer.
 */
const path=require('node:path');
const assert=require('node:assert/strict');
module.exports=async function(options){
 const {context,info,project,check}=options;
 const page=await context.newPage();const errors=[];page.on('pageerror',error=>errors.push(error.message));
 await page.goto(info.origin+'/lab/millennium.html');
 await page.addScriptTag({path:process.env.EMBER_REACT_BUNDLE});
 await page.evaluate(origin=>{
  const client=document.createElement('iframe');client.id='steam-client-window';client.src=origin+'/lab/millennium.html';
  client.style.cssText='position:fixed;inset:0;width:100%;height:100%;border:0';document.body.append(client);
 },info.origin);
 await page.frameLocator('#steam-client-window').locator('#route').waitFor();
 await page.evaluate(connection=>{
  window.fixtureConnection=connection;window.fixtureCalls=[];const routes=new Map();
  const client=document.getElementById('steam-client-window').contentWindow;
  window.fixtureRoot=window.emberCreateRoot(client.document.getElementById('route'));
  window.MILLENNIUM_API={
   ffi:(_,method)=>async()=>{
    window.fixtureCalls.push(method);
    if(method==='start_backend')return true;
    if(method!=='get_connection')throw Error('Unexpected FFI '+method);
    const response=await fetch(connection.origin+'/api/store-add',{headers:{Authorization:'Bearer '+connection.token}});
    return {...connection,add_request:(await response.json()).request};
   },
   routerHook:{addRoute:(route,component)=>routes.set(route,component),removeRoute:route=>routes.delete(route)},
   Navigation:{Navigate:route=>window.fixtureRoot.render(window.SP_REACT.createElement(routes.get(route)))},
   Millennium:{AddWindowCreateHook:()=>{}}
  };
 },info);
 await page.addScriptTag({path:path.join(project,'ember/millennium/frontend.js')});
 await check('Steam route may render in a window distinct from the plugin SharedJSContext',async()=>{
  await page.evaluate(()=>window.MILLENNIUM_API.Navigation.Navigate('/ember'));
  const frame=page.frameLocator('#steam-client-window').frameLocator('#route > iframe');
  await frame.locator('.ember-status[data-connected=true]').waitFor();
  assert(await page.evaluate(()=>document.getElementById('steam-client-window').contentDocument.querySelector('#route > iframe').ownerDocument.defaultView!==window));
 });
 await require('./check_store.cjs')({...options,hostPage:page,millennium:true,label:'Millennium cross-window',embedFrame:page.frameLocator('#steam-client-window').frameLocator('#route > iframe')});
 await check('Cross-window handoff confirms through the authenticated API without SharedJSContext message routing',async()=>{
  assert(!(await page.evaluate(()=>window.fixtureCalls)).includes('acknowledge_store_add'));
  assert.deepEqual(errors,[]);
 });
 await page.evaluate(()=>window.__emberMillennium.dispose());
 await page.close();
};
