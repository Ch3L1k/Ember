/* Ember — Copyright (C) 2026 Ember contributors.
 * GNU GPL version 3 or later; distributed without any warranty.
 * See LICENSE for the full license and warranty disclaimer.
 */
(() => {
 "use strict";
 document.documentElement.lang = "ru";
 const t=(...args)=>I18n.t(...args);
 if(new URLSearchParams(location.search).get("surface")==="steam")document.documentElement.dataset.surface="steam";
 const content = document.getElementById("content");
 const sidebar = document.querySelector(".sidebar-nav");
 const status = document.createElement("div");
 status.className = "ember-status";
 status.textContent = "Подключение…";
 document.querySelector(".sidebar-title").textContent="EMBER";
 const home = document.getElementById("page-home");
 const oldLayout = home.querySelector(".home-layout");
 const tools = document.createElement("section");
 tools.id = "page-ember-tools";
 tools.className = "page";
 tools.append(oldLayout);
 while(home.firstChild) tools.append(home.firstChild);
 oldLayout.querySelector("h1").textContent = "Все инструменты";
 oldLayout.querySelector(".page-subtitle").textContent = "Настройка игр, компонентов и манифестов";
 content.append(tools);
 home.innerHTML='<span id="ember-game-count" hidden></span>';
 function addNavigation(page, label, before) {
  const button=document.createElement("button");
  button.className="nav-item";button.dataset.page=page;
  button.innerHTML='<span class="nav-icon" aria-hidden="true">'+(page==="ember-about"?"ⓘ":"⋯")+'</span><span class="nav-label"></span>';
  button.lastChild.textContent=label;
  sidebar.insertBefore(button,before||null);
 }
 addNavigation("ember-about","Об Ember");
 const legacy=document.createElement("div");legacy.id="ember-legacy";legacy.hidden=true;legacy.inert=true;document.body.append(legacy);
 const allowed=new Set(["store","ember-library","ember-tools","ember-settings","ember-about"]);
 for(const route of ["fixgame","downgrade","cloudsaves","linuxguide","tools","ember-tools","settings","downloads"]){
  const page=document.getElementById("page-"+route);if(page)legacy.append(page);
 }
 legacy.append(document.getElementById("page-library"));
 legacy.append(home);home.classList.remove("active");
 const connection=document.createElement("div");connection.className="ember-connection-indicator";connection.append(status);document.querySelector(".sidebar").append(connection);
 tools.id="ember-legacy-home";
 sidebar.querySelector('[data-page="library"]').dataset.page="ember-tools";
 const toolsPage=document.createElement("section");toolsPage.id="page-ember-tools";toolsPage.className="page";content.append(toolsPage);
 addNavigation("ember-library","Библиотека",sidebar.querySelector('[data-page="ember-tools"]'));
 const libraryPage=document.createElement("section");libraryPage.id="page-ember-library";libraryPage.className="page";content.append(libraryPage);
 for(const button of [...sidebar.querySelectorAll(".nav-item[data-page]")]){
  if(button.dataset.page==="settings")button.dataset.page="ember-settings";
  if(!allowed.has(button.dataset.page))button.remove();
 }
 document.querySelector(".sidebar-bottom").hidden=true;
 document.getElementById("btn-logs").hidden=true;
 if(performance.getEntriesByType("navigation")[0]?.type!=="reload" || !allowed.has(localStorage.getItem("currentPage")))localStorage.setItem("currentPage","store");
 for(const [route,label] of [["store","Каталог"],["ember-tools","Инструменты"],["ember-settings","Настройки"]]){
  const node=sidebar.querySelector('[data-page="'+route+'"] .nav-label');node.removeAttribute("data-i18n");node.textContent=label;
 }
 const navigationIcons={"home":"<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path d=\"M3 3h18v18H3V3zm3 4v4h5V7H6zm0 7v2h12v-2H6zm7-7v4h5V7h-5z\"/></svg>","store":"<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path d=\"M2 3h3l2 12h12l3-9H6.1l-.5-3H2zm7 14a2 2 0 1 0 0 4 2 2 0 0 0 0-4zm9 0a2 2 0 1 0 0 4 2 2 0 0 0 0-4z\"/></svg>","ember-tools":"<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path d=\"M2 2h8v8H2V2zm12 0h8v8h-8V2zM2 14h8v8H2v-8zm12 0h8v8h-8v-8z\"/></svg>","downloads":"<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path d=\"M9 2h6v10h5l-8 8-8-8h5V2zM2 19h3v3h14v-3h3v5H2v-5z\"/></svg>","ember-settings":"<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path d=\"m10 1-1 3-2 1-3-1-3 5 3 2v2l-3 2 3 5 3-1 2 1 1 3h5l1-3 2-1 3 1 3-5-3-2v-2l3-2-3-5-3 1-2-1-1-3h-5zm2.5 7a4 4 0 1 1 0 8 4 4 0 0 1 0-8z\"/></svg>","ember-about":"<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path fill-rule=\"evenodd\" d=\"M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm0 2a8 8 0 1 1 0 16 8 8 0 0 1 0-16zm-1 3h2v2h-2V7zm0 4h2v6h-2v-6z\"/></svg>"};
 for(const [route,markup] of Object.entries(navigationIcons)){
  const oldIcon=sidebar.querySelector('[data-page="'+route+'"] .nav-icon');if(oldIcon){const host=document.createElement("span");host.className="nav-icon";host.innerHTML=markup;oldIcon.replaceWith(host);}
 }
 sidebar.querySelector('[data-page="ember-library"] .nav-icon').innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 3h5v18H2V3zm7 0h5v18H9V3zm7 1 4-1 4 17-4 1-4-17z"/></svg>';
 const store=document.getElementById("page-store");
 store.querySelector("h1").textContent="Каталог";
 store.querySelector(".page-subtitle").textContent="Поиск и добавление игр";
 document.getElementById("store-search").placeholder="Название игры или App ID";
 document.getElementById("store-select-mode").textContent="Выбрать";
 const sortingLabels={popular:"Популярные",updated:"Недавно обновлённые",newest:"Сначала новые",oldest:"Сначала старые",name_asc:"Название: А–Я",name_desc:"Название: Я–А"};
 for(const option of document.getElementById("store-sort").options)option.textContent=sortingLabels[option.value]||option.textContent;
 const preferences=document.createElement("section");preferences.id="page-ember-settings";preferences.className="page";
 preferences.innerHTML='<div class="page-header"><h1>Настройки</h1><p class="page-subtitle">Язык и подключение к каталогу</p></div><div class="ember-preference"><label for="ember-language">Язык интерфейса</label><select id="ember-language"><option value="ru">Русский</option><option value="en">English</option></select><small>Применяется сразу и сохраняется между запусками Ember.</small></div><div class="ember-preference"><label for="ember-steam-path">Папка Steam</label><input id="ember-steam-path" type="text" readonly><small>Используется Steam, установленный на этом компьютере.</small></div><details class="ember-provider"><summary>Источник каталога</summary><p>Дополнительное подключение для доступности манифестов. Просмотр каталога доступен без ключа.</p></details>';
 content.append(preferences);
 const language=document.getElementById("ember-language");
 let targetLanguage=null;
 function applyLanguage(value){targetLanguage=value;I18n.applyLanguage(value);}
 language.addEventListener("change",()=>{
  language.disabled=true;
  Bridge.callWithCallback("ember_set_language",language.value,value=>{
   if(!value){language.disabled=false;language.value=document.documentElement.lang;return;}
   if(targetLanguage!==value)applyLanguage(value);
   else if(document.documentElement.lang===value)language.disabled=false;
  });
 });
 window.addEventListener("ember:language",event=>{
  targetLanguage=event.detail.language;language.value=targetLanguage;language.disabled=false;
  if(status.dataset.connected==="true")status.textContent=readyText();
 });
 window.addEventListener("ember:rpc-error",event=>{
  if(event.detail.method==="ember_set_language"){language.disabled=false;language.value=document.documentElement.lang;}
 });
 preferences.querySelector("details").append(document.getElementById("store-connect-banner"));
 for(const id of ["store-update-list-btn","store-provider-refresh-btn","store-provider-status"])legacy.append(document.getElementById(id));
 Bridge.onReady(py=>{py.get_setting("steam_path",value=>{document.getElementById("ember-steam-path").value=value;});});
 const about=document.createElement("section");
 about.id="page-ember-about";about.className="page";
 about.innerHTML='<div class="ember-about"><h1>Об Ember</h1><div class="ember-about-hero"><img src="/ember/mark.svg" alt=""><div><h2>Ember</h2><p>Больше возможностей в твоём Steam.</p></div></div><p class="ember-about-description">Каталог игр и инструменты в привычном интерфейсе Steam.</p><div class="ember-about-card ember-about-facts"><div><span>Разработчик Ember</span><a id="ember-developer-profile" href="https://github.com/Ch3L1k" data-openurl="https://github.com/Ch3L1k" data-i18n-ignore>Ch3L1k</a></div><div><span>Версия</span><span id="ember-version" data-i18n-ignore>…</span></div></div><p class="ember-about-independent">Независимый проект. Не является продуктом Valve.</p><div class="ember-about-upstream"><h2>Основа и лицензия</h2><p>Основано на SteaMidra 6.9.1 (drappula/SFF). Авторы основы — Midrag и участники SteaMidra.</p><p><a href="https://github.com/drappula/SFF/tree/v6.9.1" target="_blank" rel="noreferrer">Исходный проект</a> · <a href="/LICENSE" target="_blank">GNU GPL v3 или новее</a> · <a href="/NOTICES" target="_blank">Авторы и сторонние компоненты</a></p><small>Исходный код и изменения включены в папку Ember. Программа распространяется без гарантий.</small></div></div>';
 content.append(about);
 content.addEventListener("click",event=>{
  const route=event.target.closest("[data-ember-route]")?.dataset.emberRoute;
  if(route) App.navigateTo(route);
 });
 function renderGames(raw) {
  let games;
  try{games=typeof raw==="string"?JSON.parse(raw):raw;}
  catch(error){console.warn("[Ember] Invalid library response",error);}
  const count=document.getElementById("ember-game-count");
  count.textContent=Array.isArray(games)?String(games.length):"Не удалось прочитать список игр";
  if(Array.isArray(games)){window.EmberGames=games;window.dispatchEvent(new CustomEvent("ember:games",{detail:games}));}
 }
 const readyText=()=>t(status.dataset.mode==='lab'?'Тестовая среда':status.dataset.steamConnected==='true'?'Подключён к Steam':'Ожидание Steam');
 window.addEventListener("ember:resync",()=>Bridge.onReady(py=>{
  py.get_installed_games(renderGames);
  const page=document.querySelector('.page.active')?.id;
  if(page==='page-library')py.refresh_library();
  if(page==='page-store')Store.onPageEnter();
 }));
 Bridge.onReady(py=>{status.dataset.connected="true";status.textContent=readyText();py.get_installed_games(renderGames);});
 Bridge.on("task_finished",raw=>{
  try{const result=typeof raw==="string"?JSON.parse(raw):raw;if(result.task==="ember_language"&&targetLanguage!==result.language)applyLanguage(result.language);if((result.task==="library_loaded"||result.task==="ember_games_loaded")&&Array.isArray(result.games))renderGames(result.games);}
  catch(error){console.debug("[Ember] Library event ignored",error);}
 });
 window.addEventListener("ember:connection",event=>{status.dataset.connected=String(event.detail.connected);status.textContent=event.detail.connected?readyText():t("Нет связи с Ember");});
 function updateIntegration(){
  EmberTransport.request("/api/info").then(info=>{
   status.dataset.mode=info.mode;
   status.dataset.steamConnected=String(!!info.integration.connected);
   if(status.dataset.connected==='true')status.textContent=readyText();
   document.getElementById("ember-version").textContent=info.version;
  }).catch(error=>{console.debug("[Ember] Integration status unavailable",error);});
 }
 updateIntegration();
 setInterval(()=>{if(!document.hidden)updateIntegration();},5000);
 const toolsScript=document.createElement("script");toolsScript.src="/ember/tools.js";document.body.append(toolsScript);
 const additions=document.createElement("script");additions.src="/ember/add-game.js";document.body.append(additions);
 const catalog=document.createElement("script");catalog.src="/ember/catalog.js";document.body.append(catalog);
 const libraryScript=document.createElement("script");libraryScript.src="/ember/library.js";document.body.append(libraryScript);
})();
