/* Ember — Copyright (C) 2026 Ember contributors.
 * GNU GPL version 3 or later; distributed without any warranty.
 * See LICENSE for the full license and warranty disclaimer.
 */
(() => {
 "use strict";
 const t=(...args)=>I18n.t(...args);
 const page=document.getElementById("page-ember-tools");
 page.innerHTML='<div class="page-header"><h1>Инструменты</h1><p class="page-subtitle">Диагностика запуска и настройки DLC</p></div><div class="ember-tool-picker"><label for="ember-tool-game">Игра</label><select id="ember-tool-game"><option value="">Выберите установленную игру</option></select><button class="btn" id="ember-tools-refresh">Обновить список</button></div><section class="ember-tool-panel"><h2>Разблокировка DLC</h2><p id="ember-dlc-description">SmokeAPI для игр со Steam API. Применяется при следующем запуске игры. Если DLC поставляется отдельными файлами, их нужно установить отдельно.</p><div class="ember-component-facts" id="ember-component-facts" hidden></div><div id="ember-dlc-status" role="status">Выберите игру для проверки совместимости.</div><div class="ember-tool-actions"><button class="btn btn-primary" id="ember-dlc-install" disabled>Включить</button><button class="btn" id="ember-dlc-remove" disabled>Удалить и восстановить файлы</button><button class="btn" id="ember-dlc-recheck" disabled>Проверить повторно</button></div></section>';
 const select=document.getElementById("ember-tool-game");
 const message=document.getElementById("ember-dlc-status");
 const install=document.getElementById("ember-dlc-install"),remove=document.getElementById("ember-dlc-remove");
 const cache=new Map(),busy=new Map();
 let games=window.EmberGames||[],entering=false,requested=null;
 function populate(){
  const previous=select.value;
  select.replaceChildren(new Option(t(games.length?"Выберите установленную игру":"Установленные игры не найдены"),""));
  for(const game of games)select.add(new Option(game.name,String(game.app_id)));
  select.value=previous;
 }
 function display(state){
  const id=select.value;
  const linux=state?.backend==='sls';
  document.getElementById('ember-dlc-description').textContent=t(linux?'Используется Linux-модуль SLSsteam. Файлы игры не заменяются. После изменения настройки перезапустите игру.':'SmokeAPI для игр со Steam API. Применяется при следующем запуске игры. Если DLC поставляется отдельными файлами, их нужно установить отдельно.');
  const pending=busy.has(id);
  page.setAttribute("aria-busy",String(pending));
  install.disabled=!id||pending||!state?.success||!state.supported||state.installed||state.conflict;
  remove.disabled=!id||pending||!state?.success||!state.installed||state.can_restore===false;
  document.getElementById("ember-dlc-recheck").disabled=!id||pending;
  install.textContent=pending && busy.get(id)==="dlc_install"?"Включаем…":"Включить";
  remove.textContent=t(pending && busy.get(id)==="dlc_remove"?(linux?"Выключаем…":"Восстанавливаем…"):(linux?"Выключить":"Удалить и восстановить файлы"));
  const facts=document.getElementById("ember-component-facts");facts.replaceChildren();facts.hidden=!id||!state?.success;
  if(state?.success){
   const labels=linux?[t('Компонент: SLSsteam'),t(state.installed?'Доступ к DLC: включён':'Доступ к DLC: выключен'),t('Файлы игры: не изменяются')]:[state.api_files!==undefined?t("Steam API: {count}",{count:state.api_files}):t(state.supported?"Steam API: найден":"Steam API: не найден"),t(state.installed?"SmokeAPI: включён":"SmokeAPI: не установлен"),state.restore_files?t("Исходные файлы: сохранены · {count}",{count:state.restore_files}):t(state.installed?"Исходные файлы: копии не найдены":"Исходные файлы: пока не изменялись")];
   for(const text of labels){const fact=document.createElement('span');fact.textContent=text;facts.append(fact);}
  }

  if(pending)message.textContent=busy.get(id)==="inspect"?"Проверяем компоненты игры…":"Выполняется… Можно продолжать пользоваться Ember.";
  else if(!id)message.textContent="Выберите игру для проверки совместимости.";
  else if(state?.message)message.textContent=state.message;
  else if(!state)message.textContent="Проверяем совместимость…";
  else if(!state.success)message.textContent="Не удалось проверить игру.";
  else if(linux)message.textContent=state.installed?'Доступ к DLC включён через Linux-модуль.':'Linux-модуль готов. Можно включить доступ к DLC.';
  else if(state.installed && state.can_restore===false)message.textContent="SmokeAPI обнаружен, но резервные копии исходных файлов не найдены. Автоматическое восстановление недоступно.";
  else if(state.conflict)message.textContent="Обнаружена другая модификация Steam API. Установка поверх неё отключена.";
  else message.textContent=state.installed?"SmokeAPI включён. Можно удалить его с восстановлением исходных файлов.":state.supported?"Steam API найден. Можно включить SmokeAPI.":"Поддерживаемый Steam API не найден. Разблокировка для этой игры недоступна.";
  message.textContent=t(message.textContent);
 }
 function run(action){
  const id=select.value;if(!id||busy.has(id))return;
  busy.set(id,action);display(cache.get(id));
  Bridge.call("ember_tool_action",id,action);
 }
 select.addEventListener("change",()=>{
  display(cache.get(select.value));
  if(select.value && !cache.has(select.value))run("inspect");
 });
 install.onclick=()=>run("dlc_install");remove.onclick=()=>run("dlc_remove");
 document.getElementById("ember-dlc-recheck").onclick=()=>run("inspect");
 document.getElementById("ember-tools-refresh").onclick=()=>{cache.clear();Bridge.call("ember_refresh_games");if(select.value)run("inspect");};
 function enter(){
  if(entering)return;entering=true;
  populate();display(cache.get(select.value));
  Bridge.onReady(py=>py.get_installed_games(raw=>{try{games=JSON.parse(raw);populate();if(requested){const value=requested;requested=null;select.value=value.id;if(select.value)run(value.action);}}finally{entering=false;}}));
 }
 window.EmberTools={openGame(id,action="inspect"){requested={id:String(id),action};App.navigateTo("ember-tools");}};
 window.addEventListener("ember:navigate",event=>{if(event.detail==="ember-tools")enter();});
 window.addEventListener("ember:games",event=>{games=event.detail;populate();display(cache.get(select.value));});
 Bridge.on("task_finished",raw=>{
  const result=JSON.parse(raw);if(result.task!=="ember_tool" || ["diagnose","repair_launch"].includes(result.action))return;
  const id=String(result.app_id);busy.delete(id);cache.set(id,result);
  if(select.value===id)display(result);
 });
 window.addEventListener("ember:rpc-error",event=>{
  if(event.detail.method!=="ember_tool_action" || ["diagnose","repair_launch"].includes(event.detail.args[1]))return;
  const id=String(event.detail.args[0]);busy.delete(id);
  cache.set(id,{success:false,message:event.detail.message});
  if(select.value===id)display(cache.get(id));
 });
 window.addEventListener("ember:language",()=>{populate();display(cache.get(select.value));});
 if(page.classList.contains("active"))enter();
})();

const diagnosticScript=document.createElement("script");diagnosticScript.src="/ember/diagnostics.js";document.body.append(diagnosticScript);
