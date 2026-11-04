/* Ember — Copyright (C) 2026 Ember contributors.
 * GNU GPL version 3 or later; distributed without any warranty.
 * See LICENSE for the full license and warranty disclaimer.
 */
(() => {
 "use strict";
 const fragment=new URLSearchParams(location.hash.slice(1));
 let token=fragment.get("token");
 try{
  if(token)sessionStorage.setItem("ember-session-token",token);
  else token=sessionStorage.getItem("ember-session-token");
 }catch(error){console.debug("[Ember] Session storage unavailable",error);}
 history.replaceState(null,"",location.pathname+location.search);
 let cursor=0,connection=null,polling=false;
 const listeners=new Map();
 function setConnection(connected,message){
  if(connection===connected)return;
  connection=connected;
  window.dispatchEvent(new CustomEvent("ember:connection",{detail:{connected,message}}));
 }
 async function request(path,data){
  const timeout=path==="/api/call"?190000:path.startsWith("/api/events")?25000:10000;
  const response=await fetch(path,{
   method:data===undefined?"GET":"POST",
   headers:{"Authorization":"Bearer "+(token||""),"Content-Type":"application/json"},
   body:data===undefined?undefined:JSON.stringify(data),
   signal:AbortSignal.timeout(timeout)
  });
  const result=await response.json();
  if(!response.ok){
   const error=new Error(response.status===401?"Сеанс Ember завершён. Перезапустите Ember Steam.":result.error||"Ember: HTTP "+response.status);
   error.status=response.status;throw error;
  }
  setConnection(true);
  return result;
 }
 function showError(error){
  console.error("[Ember]",error);
  if(window.Components)Components.showToast("error",error.message||String(error));
  if(!error.status||error.status===401)setConnection(false,error.message);
 }
 async function poll(){
  if(polling)return;
  polling=true;
  let failures=0;
  while(true){
   try{
    const payload=await request("/api/events?after="+cursor);
    cursor=payload.cursor;failures=0;
    if(payload.reset){
     window.dispatchEvent(new CustomEvent("ember:resync"));
     continue;
    }
    for(const event of payload.events){
     if(event.name==="log_message" && document.getElementById("ember-legacy"))continue;
     for(const callback of listeners.get(event.name)||[]){
      try{callback(...event.args);}catch(error){console.error("[Ember event]",error);}
     }
    }
   }catch(error){
    setConnection(false,error.status===401?error.message:"Связь с Ember потеряна");
    if(error.status===401)break;
    failures++;await new Promise(resolve=>setTimeout(resolve,Math.min(1000*failures,10000)));
   }
  }
  polling=false;
 }
 window.EmberTransport={request,showError};
 window.qt={webChannelTransport:{}};
 window.QWebChannel=function(_transport,callback){
  async function connect(){
   let info;
   try{info=await request("/api/info");}
   catch(error){
    showError(error);
    if(error.status!==401)setTimeout(connect,3000);
    return;
   }
   cursor=info.cursor||0;
   const proxy={};
   for(const signal of info.signals){
    proxy[signal]={connect(fn){
     if(!listeners.has(signal))listeners.set(signal,new Set());
     listeners.get(signal).add(fn);
    }};
   }
   for(const method of info.methods){
    proxy[method]=(...args)=>{
     const done=typeof args.at(-1)==="function"?args.pop():null;
     const action=new CustomEvent("ember:rpc-start",{detail:{method,args},cancelable:true});
     if(!window.dispatchEvent(action))return;
     request("/api/call",{method,args})
      .then(payload=>{if(done)done(payload.result);})
      .catch(error=>{window.dispatchEvent(new CustomEvent("ember:rpc-error",{detail:{method,args,message:error.message,status:error.status}}));showError(error);if(done)done(null);});
    };
   }
   try{callback({objects:{bridge:proxy}});}
   catch(error){showError(error);return;}
   poll();
  }
  connect();
 };
})();
