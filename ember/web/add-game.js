/* Ember — Copyright (C) 2026 Ember contributors.
 * GNU GPL version 3 or later; distributed without any warranty.
 * See LICENSE for the full license and warranty disclaimer.
 */
(() => {
 "use strict";
 const t=(...args)=>I18n.t(...args);
 if(window.EmberAdditions)return;
 const methods=new Set(["download_game_with_source","download_game_fastest"]);
 const operations=new Map();
 const names=new Map();
 const stages={Starting:"Подготовка…","Downloading Lua":"Получение данных игры…","Parsing Lua":"Проверка данных…","Registering app ID":"Регистрация игры…","Writing decryption keys":"Сохранение данных Steam…","Installing Lua to Steam":"Передача данных Steam…","Patching workshop config":"Обновление конфигурации…","Registering in library":"Обновление библиотеки…","Updating download tracker":"Завершение…",Complete:"Завершение…"};
 const failureMessages={"LumaCore is missing or incomplete. Restore LumaCore, then restart Steam and retry.": "LumaCore отсутствует или установлен не полностью. Восстановите LumaCore, перезапустите Steam и повторите добавление.", "Could not save the Lua in Steam. Check folder permissions and retry.": "Не удалось сохранить Lua в Steam. Проверьте доступ к папке и повторите добавление.", "The local Lua belongs to a different App ID.": "Локальный Lua относится к другой игре."};
 const phases={Starting:1,"Downloading Lua":1,"Parsing Lua":2,"Registering app ID":2,"Writing decryption keys":2,"Installing Lua to Steam":3,"Patching workshop config":3,"Registering in library":3,"Updating download tracker":4,Complete:4};
 let connected=true;
 const host=document.createElement("aside");
 host.id="ember-add-status";host.setAttribute("aria-label","Добавление игр");
 document.body.append(host);
 const pending=operation=>operation?.state==="pending";
 let clock=null;
 function updateClock(){
  for(const element of host.querySelectorAll('.ember-add-elapsed'))element.textContent=t("{seconds} с",{seconds:Math.max(0,Math.floor((Date.now()-Number(element.dataset.started))/1000))});
  for(const row of host.querySelectorAll('[data-state=pending]')){
   const operation=operations.get(row.dataset.appid),hint=row.querySelector('.ember-add-wait');
   const seconds=Math.max(0,Math.floor((Date.now()-operation.lastUpdate)/1000));
   row.dataset.waiting=String(!connected||operation.waiting);
   hint.hidden=connected&&!operation.waiting&&seconds<30;
   hint.textContent=t(!connected?"Нет связи с Ember. Ожидаем подключение…":operation.waiting?"Ожидаем подтверждения операции.":"Нет новых этапов {seconds} с. Ожидаем ответ.",{seconds});
  }
 }
 const buttons=id=>[...document.querySelectorAll('.btn-download[data-appid]')].filter(button=>button.dataset.appid===id);
 const nameFor=id=>names.get(id)||buttons(id)[0]?.dataset.name||t("Игра {id}",{id});
 function updateButtons(){
  for(const button of document.querySelectorAll('.btn-download[data-appid]')){
   const operation=operations.get(button.dataset.appid);
   if(!operation)continue;
   button.disabled=pending(operation);
   button.setAttribute("aria-busy",String(pending(operation)));
   button.classList.toggle("ember-adding",pending(operation));
   const text=t(pending(operation)?"Добавление…":operation.state==="done"?"Добавлено":"Добавить");
   if(button.textContent!==text)button.textContent=text;
  }
 }
 function render(){
  host.replaceChildren();
  for(const operation of operations.values()){
   if(operation.dismissed)continue;
   const row=document.createElement("section");row.className="ember-add-operation";row.dataset.state=operation.state;
   row.dataset.appid=operation.id;
   const title=document.createElement("strong");title.textContent=operation.name;title.title=operation.name;title.setAttribute("data-i18n-ignore","");
   const heading=document.createElement("div");heading.className="ember-add-heading";heading.append(title);
   const label=document.createElement("div");label.className="ember-add-stage";label.setAttribute("role","status");label.setAttribute("aria-live","polite");label.textContent=t(operation.message);
   const detail=document.createElement("p");detail.className="ember-add-detail";detail.textContent=(Array.isArray(operation.detail)?operation.detail:[operation.detail||""]).map(value=>t(value)).join(" ");detail.hidden=!detail.textContent;
   row.append(heading,label,detail);
   const completed=operation.state==="done"?4:Math.max(0,operation.phase-1);
   const progress=document.createElement("div");progress.className="ember-add-progress";progress.setAttribute("role","progressbar");
   progress.setAttribute("aria-label",t("Добавление игры"));progress.setAttribute("aria-valuemin","0");progress.setAttribute("aria-valuemax","4");progress.setAttribute("aria-valuenow",String(completed));
   progress.setAttribute("aria-valuetext",t(operation.state==="done"?"Данные переданы Steam":operation.state==="error"?"Не удалось завершить добавление":"Этап {current} из {total}",{current:operation.phase,total:4}));
   const percent=operation.fileProgress!==undefined&&pending(operation)?operation.fileProgress:completed*25;
   progress.style.setProperty("--ember-progress",percent+"%");
   if(operation.fileProgress!==undefined&&pending(operation)){progress.setAttribute("aria-valuemax","100");progress.setAttribute("aria-valuenow",String(percent));progress.setAttribute("aria-valuetext",Math.floor(percent)+"%");}
   const fill=document.createElement("span");fill.className="ember-add-progress-fill";progress.append(fill);row.append(progress);
   const footer=document.createElement("div");footer.className="ember-add-footer";
   if(pending(operation)){
    const active=document.createElement("span");active.className="ember-add-progress-active";progress.append(active);
    const phase=document.createElement("span");phase.className="ember-add-phase";phase.textContent=t("Этап {current} из {total}",{current:operation.phase,total:4});footer.append(phase);
   }
   if(pending(operation)){
    const spinner=document.createElement("span");spinner.className="ember-add-spinner";spinner.setAttribute("aria-hidden","true");heading.append(spinner);
    const elapsed=document.createElement("span");elapsed.className="ember-add-elapsed";elapsed.dataset.started=String(operation.started);footer.append(elapsed);
    const cancel=document.createElement("button");cancel.className="btn";cancel.textContent=t("Отмена");cancel.disabled=!!operation.cancelling;
    cancel.onclick=()=>{operation.cancelling=true;operation.message="Отмена добавления…";Bridge.call("download_cancel_active",operation.id,false);render();};footer.append(cancel);
   }else{
    const dismiss=document.createElement("button");dismiss.className="btn";dismiss.textContent=t("Понятно");dismiss.onclick=()=>{operation.dismissed=true;render();};footer.append(dismiss);
    if(operation.state==="error"){
     const retry=document.createElement("button");retry.className="btn btn-primary";retry.textContent=t("Повторить");retry.onclick=()=>Components.showDownloadModal(operation.id,operation.name,"win32");footer.append(retry);
    }
   }
   row.append(footer);
   if(pending(operation)){const hint=document.createElement("p");hint.className="ember-add-wait";hint.hidden=true;row.append(hint);}
   host.append(row);
  }
  updateButtons();
  updateClock();
  if([...operations.values()].some(pending)){if(!clock)clock=setInterval(updateClock,1000);}
  else if(clock){clearInterval(clock);clock=null;}
 }
 function begin(id){
  id=String(id||"");
  if(!/^\d+$/.test(id))return;
  operations.set(id,{id,name:nameFor(id),state:"pending",message:"Начинаем добавление…",started:Date.now(),lastUpdate:Date.now(),phase:1,waiting:false});
  render();
 }
 function fail(operation,message){
  operation.state="error";operation.message="Не удалось завершить добавление";operation.detail=message||"Повторите попытку и проверьте подключение.";render();
 }
 window.EmberAdditions={handles:id=>operations.has(String(id)),isPending:id=>pending(operations.get(String(id)))};
 window.addEventListener("ember:rpc-start",event=>{
  if(!methods.has(event.detail.method))return;
  const id=String(event.detail.args[0]);
  if(pending(operations.get(id))){event.preventDefault();return;}
  begin(id);
 });
 window.addEventListener("ember:rpc-error",event=>{
  if(!methods.has(event.detail.method))return;
  const operation=operations.get(String(event.detail.args[0]));
  if(!operation)return;
  if(!event.detail.status || (event.detail.status===504 && event.detail.message.includes("ещё выполняется"))){
   operation.waiting=true;
   operation.message="Ожидаем подтверждение…";operation.detail=[event.detail.message,"Не запускайте добавление повторно, пока результат неизвестен."];render();
  }else fail(operation,event.detail.message);
 });
 document.addEventListener("click",event=>{
  const button=event.target.closest('.btn-download[data-appid]');
  if(button && pending(operations.get(button.dataset.appid))){event.preventDefault();event.stopImmediatePropagation();}
 },true);
 Bridge.on("download_progress",raw=>{
  const data=JSON.parse(raw);const id=String(data.app_id||"");
  const operation=operations.get(id);if(!pending(operation))return;
  operation.lastUpdate=Date.now();operation.waiting=false;
  operation.phase=Math.max(operation.phase,phases[data.status]||operation.phase);
  if(data.error || /^Error:/.test(data.status||""))operation.detail=failureMessages[data.status.replace(/^Error:\s*/,"")]||data.status.replace(/^Error:\s*/,"");
  else {operation.detail="";operation.message=stages[data.status]||data.status||operation.message;}
  render();
 });
 Bridge.on("task_finished",raw=>{
  const data=JSON.parse(raw);if(data.task!=="download_fastest")return;
  const operation=operations.get(String(data.app_id));if(!operation)return;
  if(!data.success){
   fail(operation,data.source_empty?"В выбранном источнике нет данных этой игры. Нажмите «Повторить» и выберите другой источник.":data.cancelled?"Добавление отменено.":operation.detail||data.message);
   return;
  }
  operation.state="done";operation.message="Данные переданы Steam";
  operation.detail="Откройте библиотеку Steam. Обычно игра появляется без перезапуска; подтверждения её появления от Steam пока нет. Если она не появилась, перезапустите Steam. Для скачивания файлов нажмите «Установить» в библиотеке Steam.";
  render();
 });
 window.addEventListener("ember:connection",event=>{
  connected=event.detail.connected;
  for(const operation of operations.values())if(pending(operation)){
   operation.detail=event.detail.connected?"Связь восстановлена. Ожидаем результат; не запускайте добавление повторно.":"Связь с Ember потеряна. Результат пока неизвестен; не запускайте добавление повторно.";
  }
  render();
 });
 let modalName=null;
 const modal=document.getElementById("download-modal");
 modal.classList.add("ember-add-modal");
 modal.setAttribute("role","dialog");modal.setAttribute("aria-modal","true");modal.setAttribute("aria-labelledby","download-modal-title");
 const body=modal.querySelector(".modal-body"),modalFooter=modal.querySelector(".modal-footer");
 const settings=document.createElement("details");settings.className="ember-add-settings";
 const summary=document.createElement("summary");
 const summaryLabel=document.createElement("span"),summaryValue=document.createElement("span");summaryValue.className="ember-add-source-value";
 summary.append(summaryLabel,summaryValue);settings.append(summary);
 const settingsBody=document.createElement("div");settingsBody.className="ember-add-settings-body";settings.append(settingsBody);
 const alternatives=document.createElement("details");alternatives.className="ember-add-alternatives";
 const alternativesSummary=document.createElement("summary");alternatives.append(alternativesSummary);
 const alternativesBody=document.createElement("div");alternativesBody.className="ember-add-alternatives-body";alternatives.append(alternativesBody);
 const osRow=document.getElementById("dl-target-os").parentElement;
 const destinationRow=document.getElementById("dl-ddmod-dest-path").parentElement.parentElement;
 const primary=document.getElementById("dl-fastest");
 const alternateNodes=new Set([osRow,destinationRow,document.getElementById("dl-crack-banner"),document.getElementById("dl-ddmod"),document.getElementById("dl-older")]);
 for(const node of [...body.children]){
  if(node===primary)continue;
  (alternateNodes.has(node)?alternativesBody:settingsBody).append(node);
 }
 settingsBody.append(alternatives);
 const intro=document.createElement("div");intro.className="ember-add-intro";
 intro.innerHTML='<span class="ember-add-intro-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M4 3h5v18H4zM9 3h5v18H9zM16 4l4-1 4 17-4 1z"/></svg></span><div><strong></strong><p></p></div>';
 body.append(intro,settings);
 primary.className="btn btn-primary ember-add-confirm";primary.removeAttribute("data-tooltip");
 primary.querySelector("svg")?.remove();
 primary.querySelector(".dl-desc").hidden=true;
 modalFooter.append(primary);
 const picker=modal.querySelector(".dl-source-picker");picker.hidden=true;
 const sourceField=document.createElement("div");sourceField.className="ember-add-source-field";
 const sourceLabel=document.createElement("label");sourceLabel.htmlFor="ember-add-source";
 const sourceSelect=document.createElement("select");sourceSelect.id="ember-add-source";
 for(const radio of picker.querySelectorAll("input")){
  const option=document.createElement("option");option.value=radio.value;sourceSelect.append(option);
 }
 sourceField.append(sourceLabel,sourceSelect);settingsBody.prepend(sourceField);
 const sourceNames={freelua:"Бесплатные источники",hubcap:"Hubcap",ryuu:"Ryuu",depotbox:"DepotBox",local:"Локальный файл"};
 const localWarning=document.createElement("p");localWarning.className="ember-add-local-warning";localWarning.setAttribute("role","alert");localWarning.hidden=true;
 document.getElementById("dl-local-row").append(localWarning);
 const keyDialog=document.createElement("dialog");keyDialog.id="ember-provider-key";
 keyDialog.setAttribute("aria-labelledby","ember-provider-key-title");
 keyDialog.innerHTML='<form><h2 id="ember-provider-key-title"></h2><p class="ember-key-description"></p><label for="ember-provider-key-input">API key</label><input id="ember-provider-key-input" type="password" autocomplete="off" spellcheck="false" required><p class="ember-key-error" role="alert" hidden></p><div class="ember-key-actions"><button type="button" class="btn modal-cancel"></button><button type="submit" class="btn btn-primary"></button></div></form>';
 document.body.append(keyDialog);
 const keyInput=keyDialog.querySelector("input"),keyError=keyDialog.querySelector(".ember-key-error");
 const keySave=keyDialog.querySelector('[type="submit"]');
 const providers={hubcap:["morrenus_key"],ryuu:["ryuu_key","ryuu_api_key"],depotbox:["depotbox_key"]};
 let keyRequest=null,checkingKey=false,approvedAddition=null;
 function sameAddition(request){return !modal.classList.contains("hidden")&&primary.dataset.appid===request.app&&sourceSelect.value===request.source;}
 function continueAddition(request){
  if(!sameAddition(request))return;
  approvedAddition=request;primary.click();
 }
 keyDialog.querySelector(".modal-cancel").onclick=()=>keyDialog.close();
 keyDialog.addEventListener("close",()=>{keyInput.value="";keyRequest=null;primary.focus({preventScroll:true});});
 keyDialog.addEventListener("keydown",event=>{if(event.key==="Escape"){event.preventDefault();event.stopPropagation();keyDialog.close();}});
 keyDialog.querySelector("form").addEventListener("submit",async event=>{
  event.preventDefault();
  const request=keyRequest,value=keyInput.value.trim();
  if(!request||!value||keySave.disabled)return;
  keySave.disabled=true;keyError.hidden=true;
  try{
   await EmberTransport.request("/api/call",{method:"set_setting",args:[providers[request.source][0],value]});
   const saved=await EmberTransport.request("/api/call",{method:"get_setting",args:[providers[request.source][0]]});
   if(saved.result!==value)throw new Error("key-save-failed");
   if(!keyDialog.open||keyRequest!==request)return;
   keyDialog.close();
   window._updateDownloadSourceHint?.();
   continueAddition(request);
  }catch(error){
   console.debug("[Ember] Provider key could not be saved");
   keyError.textContent=t("Не удалось сохранить ключ. Повторите попытку.");keyError.hidden=false;
  }finally{keySave.disabled=false;}
 });
 function syncSource(){
  const selected=picker.querySelector("input:checked")?.value||"freelua";
  sourceSelect.value=selected;summaryValue.textContent=t(sourceNames[selected]||selected);
  if(selected!=="local")localWarning.hidden=true;
 }
 sourceSelect.addEventListener("change",()=>{
  const radio=[...picker.querySelectorAll("input")].find(input=>input.value===sourceSelect.value);
  if(radio){radio.checked=true;radio.dispatchEvent(new Event("change",{bubbles:true}));}
 });
 picker.addEventListener("change",syncSource);
 primary.addEventListener("click",async event=>{
  const request={source:sourceSelect.value,app:primary.dataset.appid};
  if(approvedAddition?.source===request.source&&approvedAddition?.app===request.app){approvedAddition=null;return;}
  if(sourceSelect.value==="local"&&!document.getElementById("dl-local-lua-path").value){
   event.preventDefault();event.stopImmediatePropagation();settings.open=true;
   localWarning.hidden=false;localWarning.textContent=t("Сначала выберите локальный файл.");
   document.getElementById("dl-local-lua-browse").focus();
   return;
  }
  if(!providers[request.source])return;
  event.preventDefault();event.stopImmediatePropagation();
  if(checkingKey)return;
  checkingKey=true;primary.setAttribute("aria-busy","true");
  try{
   const results=await Promise.all(providers[request.source].map(key=>EmberTransport.request("/api/call",{method:"get_setting",args:[key]})));
   if(!sameAddition(request))return;
   if(results.some(value=>typeof value.result==="string"&&value.result.trim())){continueAddition(request);return;}
   keyRequest=request;keyInput.value="";keyError.hidden=true;
   keyDialog.querySelector("h2").textContent=t("API-ключ {provider}",{provider:sourceNames[request.source]});
   keyDialog.querySelector(".ember-key-description").textContent=t("Для этого источника нужен API-ключ. Введите его, чтобы продолжить добавление.");
   keyDialog.querySelector(".modal-cancel").textContent=t("Отмена");
   keySave.textContent=t("Сохранить и продолжить");
   keyDialog.showModal();keyInput.focus();
  }catch(error){EmberTransport.showError(error);}
  finally{checkingKey=false;primary.removeAttribute("aria-busy");}
 },true);
 for(const id of ["dl-fastest-title","dl-fastest-desc"])document.getElementById(id).removeAttribute("data-i18n");
 function renderModal(){
  if(modalName===null)return;
  document.getElementById("download-modal-title").textContent=t("Добавить: {name}",{name:modalName});
  document.getElementById("download-modal-title").title=modalName;
  document.getElementById("dl-fastest-title").textContent=t("Добавить в Steam");
  document.getElementById("dl-fastest-desc").textContent=t("Передать данные игры Steam. После завершения откройте библиотеку Steam для установки.");
  intro.querySelector("strong").textContent=t("Добавление в библиотеку");
  intro.querySelector("p").textContent=t("После добавления откройте библиотеку Steam, чтобы установить игру.");
  summaryLabel.textContent=t("Источник и настройки");sourceLabel.textContent=t("Источник данных");
  alternativesSummary.textContent=t("Другие способы установки");
  for(const option of sourceSelect.options)option.textContent=t(sourceNames[option.value]);
  document.getElementById("dl-ddmod").querySelector(".dl-title").textContent=t("Загрузить файлы отдельно");
  document.getElementById("dl-ddmod").querySelector(".dl-desc").textContent=t("Встроенный загрузчик. Резервный способ — DDMod (.NET 9).");
  document.getElementById("dl-older").querySelector(".dl-title").textContent=t("Выбрать версию игры");
  document.getElementById("dl-older").querySelector(".dl-desc").textContent=t("Установка предыдущей версии через Steam или DDMod.");
  osRow.querySelector("span").textContent=t("Операционная система");
  document.getElementById("dl-depot-advanced").textContent=t("Выбрать компоненты");
  destinationRow.firstElementChild.textContent=t("Папка для отдельной загрузки");
  document.getElementById("dl-ddmod-dest-path").placeholder=t("Выберите папку");
  for(const id of ["dl-local-lua-browse","dl-manifest-folder-browse","dl-ddmod-dest-browse"])document.getElementById(id).textContent=t("Обзор");
  modal.querySelector(".modal-cancel").textContent=t("Отмена");
  syncSource();
 }
 window.addEventListener("ember:language",()=>{render();renderModal();});
 const observer=new MutationObserver(updateButtons);
 observer.observe(document.getElementById("page-store"),{childList:true,subtree:true});
 const original=Components.showDownloadModal;
 Components.showDownloadModal=(id,name,platform)=>{
  if(pending(operations.get(String(id))))return;
  names.set(String(id),name);
  modalName=name;
  localWarning.hidden=true;
  original(id,name,platform);
  primary.style.removeProperty("display");primary.hidden=false;
  settings.open=false;alternatives.open=false;alternatives.hidden=platform==="linux";
  renderModal();
  requestAnimationFrame(()=>primary.focus({preventScroll:true}));
 };
 const openedStoreRequests=new Set();
 let storePlatform=null;
 function openStoreRequest(request){
  if(!storePlatform||!Bridge.isReady()||!request||typeof request.request_id!=="string"||request.request_id.length>80||typeof request.app_id!=="string"||!(/^[1-9]\d{0,9}$/).test(request.app_id)||Number(request.app_id)>4294967295||typeof request.name!=="string"||request.name.length>512)return false;
  if(!openedStoreRequests.has(request.request_id)){
   App.navigateTo("store");
   Components.hideModal("confirm-dialog");
   Components.showDownloadModal(request.app_id,request.name,storePlatform);
   openedStoreRequests.add(request.request_id);
   if(openedStoreRequests.size>64)openedStoreRequests.delete(openedStoreRequests.values().next().value);
  }
  return true;
 }
 let pollingStore=false;
 async function pollStoreRequest(){
  if(pollingStore||!storePlatform)return;
  pollingStore=true;
  try{
   const value=await EmberTransport.request("/api/store-add");
   if(value.request&&openStoreRequest(value.request))await EmberTransport.request("/api/store-add",{action:"acknowledge",request_id:value.request.request_id});
  }catch(error){console.debug("[Ember] Store handoff unavailable",error);}
  finally{pollingStore=false;}
 }
 Bridge.onReady(()=>Bridge.callWithCallback("get_platform",value=>{
  storePlatform=value;
  pollStoreRequest();setInterval(pollStoreRequest,1500);
 }));
})();
