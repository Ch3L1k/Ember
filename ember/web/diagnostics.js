/* Ember — Copyright (C) 2026 Ember contributors.
 * GNU GPL version 3 or later; without any warranty. See LICENSE. */
(() => {
 "use strict";
 const t=(...args)=>I18n.t(...args),select=document.getElementById('ember-tool-game');
 const panel=document.createElement('section');panel.className='ember-tool-panel';
 panel.innerHTML='<h2>Проблемы с запуском</h2><p>Проверка файлов и окружения Proton. Исправления применяются только к выбранной игре, с сохранением резервной копии.</p><div class="ember-tool-actions"><button class="btn btn-primary" id="ember-diagnose" disabled>Найти проблемы</button><button class="btn" id="ember-repair-launch" disabled>Исправить найденное</button></div><div id="ember-diagnostic-report" role="status" style="margin-top:16px;line-height:1.6;overflow-wrap:anywhere"></div>';
 document.querySelector('#page-ember-tools .ember-tool-panel').before(panel);
 const check=panel.querySelector('#ember-diagnose'),fix=panel.querySelector('#ember-repair-launch'),report=panel.querySelector('#ember-diagnostic-report');
 const states=new Map(),pending=new Map();
 function render(){
  const id=select.value,state=states.get(id),action=pending.get(id);
  check.disabled=!id||!!action;fix.disabled=!id||!!action||!state?.success||!state?.repairable;
  check.textContent=t(action==='diagnose'?'Проверяем…':'Найти проблемы');
  fix.textContent=t(action==='repair_launch'?'Исправляем…':'Исправить найденное');
  panel.setAttribute('aria-busy',String(!!action));report.replaceChildren();
  if(action){report.textContent=t(action==='repair_launch'?'Копируем и проверяем окружение Proton. Дождитесь завершения перед запуском игры.':'Проверяем установку…');return;}
  if(!state){report.textContent=t('Выберите игру и нажмите «Найти проблемы».');return;}
  for(const text of [...(state.checks||[]),state.message,state.backup&&t('Резервная копия: {path}',{path:state.backup})].filter(Boolean)){
   const row=document.createElement('div');row.textContent=t(text);report.append(row);
  }
 }
 function run(action){
  const id=select.value;if(!id||pending.has(id))return;
  pending.set(id,action);render();Bridge.call('ember_tool_action',id,action);
 }
 check.onclick=()=>run('diagnose');fix.onclick=()=>run('repair_launch');select.addEventListener('change',render);
 Bridge.on('task_finished',raw=>{
  const value=JSON.parse(raw);if(value.task!=='ember_tool'||!['diagnose','repair_launch'].includes(value.action))return;
  const id=String(value.app_id);pending.delete(id);states.set(id,value);render();
 });
 window.addEventListener('ember:rpc-error',event=>{
  const v=event.detail;if(v.method!=='ember_tool_action'||!['diagnose','repair_launch'].includes(v.args[1]))return;
  const id=String(v.args[0]);pending.delete(id);states.set(id,{success:false,message:v.message});render();
 });
 window.addEventListener('ember:games',render);window.addEventListener('ember:language',render);render();
})();
