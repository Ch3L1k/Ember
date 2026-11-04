/* Ember — Copyright (C) 2026 Ember contributors.
 * GNU GPL version 3 or later; distributed without any warranty.
 * See LICENSE for the full license and warranty disclaimer.
 */
(() => {
 "use strict";
 const t=(...args)=>I18n.t(...args);
 const page=document.getElementById("page-store"),search=document.getElementById("store-search");
 let data={revision:-1,pins:[],searches:[],recent:[]},view="all",saving=new Set();
 const header=page.querySelector(".page-header");
 header.classList.add("ember-catalog-heading");
 header.querySelector(".page-subtitle").textContent="Найдите игру, отложите на потом или добавьте в Steam";
 const shortcut=document.createElement("button");shortcut.className="btn ember-search-shortcut";shortcut.textContent="Ctrl+K · Поиск";shortcut.onclick=()=>{search.focus();search.select();};header.append(shortcut);
 document.getElementById("store-search-btn").textContent="Найти";
 const searchButton=document.getElementById("store-search-btn");
 const searchStatus=document.createElement("div");searchStatus.id="ember-search-status";searchStatus.hidden=true;
 const searchLabel=document.createElement("span");searchLabel.setAttribute("role","status");searchLabel.setAttribute("aria-live","polite");
 const searchElapsed=document.createElement("span");searchElapsed.className="ember-search-elapsed";
 searchStatus.append(searchLabel,searchElapsed);page.querySelector(".store-controls").after(searchStatus);
 let searchState={busy:false,error:""},searchStarted=0,searchClock=null,connected=true;
 function renderSearch(){
  page.setAttribute("aria-busy",String(searchState.busy));
  searchButton.classList.toggle("ember-searching",searchState.busy);
  searchButton.setAttribute("aria-busy",String(searchState.busy));
  searchButton.textContent=t(searchState.busy?"Ищем…":"Найти");
  searchStatus.hidden=!searchState.busy&&!searchState.error;
  searchStatus.dataset.busy=String(searchState.busy);searchStatus.dataset.error=String(!!searchState.error);
  const seconds=Math.max(0,Math.floor((Date.now()-searchStarted)/1000));
  searchLabel.textContent=searchState.error?t("Поиск не завершён. Повторите попытку."):!connected?t("Нет связи с Ember. Ожидаем подключение…"):t(seconds>=30?"Источник отвечает дольше обычного. Ожидаем результаты…":"Ищем игры…");
  searchElapsed.textContent=searchState.busy?t("{seconds} с",{seconds}):"";
 }
 window.addEventListener("ember:search-state",event=>{
  if(event.detail.busy&&(!searchState.busy||event.detail.requestId!==searchState.requestId))searchStarted=Date.now();
  searchState=event.detail;renderSearch();
  if(searchState.busy&&!searchClock)searchClock=setInterval(renderSearch,1000);
  else if(!searchState.busy&&searchClock){clearInterval(searchClock);searchClock=null;}
 });
 window.addEventListener("ember:connection",event=>{connected=event.detail.connected;renderSearch();});
 window.addEventListener("ember:language",renderSearch);
 const tabs=document.createElement("div");tabs.className="ember-catalog-tabs";tabs.setAttribute("role","group");tabs.setAttribute("aria-label","Раздел каталога");
 for(const [key,label] of [["all","Все игры"],["pins","Отложено"],["recent","История добавлений"]]){
  const button=document.createElement("button");button.className="ember-catalog-tab";button.dataset.view=key;button.textContent=label;button.setAttribute("aria-pressed",String(key===view));button.onclick=()=>selectView(key);tabs.append(button);
 }
 header.after(tabs);
 const history=document.createElement("div");history.id="ember-search-history";history.setAttribute("aria-label","Недавние поиски");
 page.querySelector(".store-controls").after(history);
 const saved=document.createElement("section");saved.id="ember-saved-content";saved.hidden=true;saved.setAttribute("aria-label","Сохранённые игры и действия");history.after(saved);

 function apply(value){
  if(!value || value.revision<data.revision)return;
  data=value;
  renderHistory();renderSaved();updatePins();
  window.dispatchEvent(new CustomEvent("ember:workspace",{detail:data}));
 }
 function update(request,done){
  Bridge.onReady(py=>py.ember_update_workspace(JSON.stringify(request),raw=>{
   if(raw){try{apply(JSON.parse(raw));if(done)done();}catch(error){EmberTransport.showError(error);}}
  }));
 }
 function load(){Bridge.onReady(py=>py.ember_get_workspace(raw=>{if(raw)apply(JSON.parse(raw));}));}
 function selectView(next){
  view=next;page.dataset.catalogView=next;
  saved.hidden=next==="all";
  for(const button of tabs.children)button.setAttribute("aria-pressed",String(button.dataset.view===next));
  renderSaved();
 }
 function renderHistory(){
  history.replaceChildren();
  if(!data.searches.length)return;
  const title=document.createElement("span");title.className="ember-recent-label";title.textContent="Недавно искали";history.append(title);
  for(const query of data.searches.slice(0,5)){
   const button=document.createElement("button");button.className="ember-search-chip";button.textContent=query;button.onclick=()=>{selectView("all");search.value=query;document.getElementById("store-search-btn").click();};history.append(button);
  }
  const clear=document.createElement("button");clear.className="ember-text-button";clear.textContent="Очистить";clear.setAttribute("aria-label","Очистить историю поиска");clear.onclick=()=>update({action:"clear_searches"});history.append(clear);
 }
 function renderSaved(){
  tabs.querySelector('[data-view="pins"]').textContent=data.pins.length?t("Отложено · {count}",{count:data.pins.length}):t("Отложено");
  if(view==="all")return;
  saved.replaceChildren();
  const rows=view==="pins"?data.pins:data.recent;
  if(!rows.length){
   const empty=document.createElement("div");empty.className="ember-saved-empty";
   const title=document.createElement("h2");title.textContent=view==="pins"?"Игры на потом":"Здесь будут результаты добавлений";
   const text=document.createElement("p");text.textContent=view==="pins"?"Нажмите звёздочку на карточке игры. Список сохранится после перезапуска Ember.":"Успешные и неудачные попытки сохраняются здесь. Игровые файлы устанавливаются в Steam.";
   empty.append(title,text);saved.append(empty);return;
  }
  if(view==="pins"){
   const grid=document.createElement("div");grid.className="game-grid ember-pinned-grid";
   for(const game of rows)grid.append(Components.createGameCard(game));
   saved.append(grid);
  }else{
   const toolbar=document.createElement("div");toolbar.className="ember-activity-toolbar";
   const hint=document.createElement("span");hint.textContent="Последние 12 игр · сохраняется между запусками";
   const clear=document.createElement("button");clear.className="ember-text-button";clear.textContent="Очистить историю";clear.onclick=()=>update({action:"clear_recent"});toolbar.append(hint,clear);saved.append(toolbar);
   for(const game of rows){
    const row=document.createElement("article");row.className="ember-activity-row";
    const title=document.createElement("strong");title.textContent=game.name;
    const result=document.createElement("span");result.className="ember-activity-result";result.dataset.success=String(game.success);result.textContent=game.success?"Данные переданы Steam":"Добавление не завершено";
    const when=document.createElement("time");when.dateTime=new Date(game.time*1000).toISOString();when.textContent=new Date(game.time*1000).toLocaleString(document.documentElement.lang==="en"?"en-US":"ru-RU",{day:"numeric",month:"short",hour:"2-digit",minute:"2-digit"});
    const button=document.createElement("button");button.className="btn";button.textContent="Найти в каталоге";button.onclick=()=>{selectView("all");search.value=game.app_id;document.getElementById("store-search-btn").click();};
    row.append(title,result,when,button);saved.append(row);
   }
  }
 }
 function updatePins(){
  const ids=new Set(data.pins.map(game=>game.app_id));
  for(const button of document.querySelectorAll('.ember-pin[data-appid]')){
   const pinned=ids.has(button.dataset.appid);button.setAttribute("aria-pressed",String(pinned));
   button.title=t(pinned?"Убрать из отложенного":"Отложить на потом");
   button.setAttribute("aria-label",button.title+": "+button.dataset.name);
   button.disabled=saving.has(button.dataset.appid);
  }
 }
 function decorate(card,game){
  if(!/^\d{1,10}$/.test(String(game.app_id)) || card.querySelector(".ember-pin"))return card;
  const button=document.createElement("button");button.className="ember-pin";button.dataset.appid=String(game.app_id);button.dataset.name=String(game.name||t("Игра {id}",{id:game.app_id}));
  button.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 2 3.09 6.26L22 9.27l-5 4.87L18.18 21 12 17.76 5.82 21 7 14.14 2 9.27l6.91-1.01L12 2Z"/></svg>';
  const pinned=data.pins.some(item=>item.app_id===String(game.app_id));button.setAttribute("aria-pressed",String(pinned));button.title=t(pinned?"Убрать из отложенного":"Отложить на потом");button.setAttribute("aria-label",button.title+": "+button.dataset.name);
  button.addEventListener("click",event=>{
   event.preventDefault();event.stopPropagation();const id=button.dataset.appid;if(saving.has(id))return;
   saving.add(id);updatePins();
   Bridge.onReady(py=>py.ember_update_workspace(JSON.stringify({action:"toggle_pin",game:{app_id:id,name:button.dataset.name}}),raw=>{
    saving.delete(id);if(raw)apply(JSON.parse(raw));else updatePins();
   }));
  });
  card.append(button);return card;
 }
 for(const method of ["createGameCard","createGameListItem"]){const original=Components[method];Components[method]=(...args)=>decorate(original(...args),args[0]);}
 let decorationPending=false;
 const observer=new MutationObserver(()=>{
  if(decorationPending)return;decorationPending=true;requestAnimationFrame(()=>{
   decorationPending=false;
   for(const card of page.querySelectorAll('#store-grid .game-card,#store-list .game-list-item')){
    const button=card.querySelector('.btn-download');if(button)decorate(card,{app_id:button.dataset.appid,name:button.dataset.name});
   }
  });
 });
 observer.observe(page,{childList:true,subtree:true});
 function remember(){
  const query=search.value.trim();selectView("all");
  if(query)update({action:"remember_search",query});
 }
 document.addEventListener("click",event=>{if(event.target.closest('#store-search-btn'))remember();},true);
 search.addEventListener("keydown",event=>{if(event.key==="Enter")remember();},true);
 window.addEventListener("keydown",event=>{
  if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==="k"){
   event.preventDefault();App.navigateTo("store");selectView("all");search.focus();search.select();
  }
 });
 window.addEventListener("ember:rpc-start",event=>{
  if(!["download_game_with_source","download_game_fastest"].includes(event.detail.method))return;
  const id=String(event.detail.args[0]);const button=[...document.querySelectorAll('.btn-download[data-appid]')].find(item=>item.dataset.appid===id);
  if(button)update({action:"note_game",game:{app_id:id,name:button.dataset.name}});
 });
 window.addEventListener("ember:language",()=>{renderHistory();renderSaved();updatePins();});
 Bridge.on("task_finished",raw=>{const result=JSON.parse(raw);if(result.task==="ember_workspace")apply(result.workspace);});
 window.addEventListener("ember:resync",load);
 window.EmberCatalog={get workspace(){return data;},selectView};
 selectView("all");load();
 if(Store.getSearchState)window.dispatchEvent(new CustomEvent("ember:search-state",{detail:Store.getSearchState()}));
})();
