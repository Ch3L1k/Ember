/* Ember — Copyright (C) 2026 Ember contributors.
 * GNU GPL version 3 or later; distributed without any warranty.
 * See LICENSE for the full license and warranty disclaimer.
 */
(() => {
 "use strict";
 const t=(...args)=>I18n.t(...args),page=document.getElementById("page-ember-library");
 page.innerHTML='<div class="page-header"><h1></h1><p class="page-subtitle"></p></div><div class="ember-library-controls"><input id="ember-library-search" type="search"><select id="ember-library-filter"></select><button class="btn" id="ember-library-refresh"></button></div><div id="ember-library-status" role="status" aria-live="polite"></div><div id="ember-library-summary"></div><div id="ember-library-list"></div><div class="ember-library-pagination"><button class="btn" id="ember-library-previous"></button><span id="ember-library-position"></span><button class="btn" id="ember-library-next"></button></div>';
 const search=document.getElementById("ember-library-search"),filter=document.getElementById("ember-library-filter"),list=document.getElementById("ember-library-list"),status=document.getElementById("ember-library-status"),refresh=document.getElementById("ember-library-refresh");
 const previous=document.getElementById("ember-library-previous"),next=document.getElementById("ember-library-next");
 let games=[],loading=false,loaded=false,dirty=true,lastLoad=0,current=0,message="",lastRemoved=null,searchTimer;
 function label(){
  page.querySelector('h1').textContent=t("Библиотека");
  page.querySelector('.page-subtitle').textContent=t("Добавленные через Ember и установленные игры Steam");
  search.placeholder=t("Поиск по названию или App ID");search.setAttribute('aria-label',search.placeholder);
  const selected=filter.value;filter.replaceChildren();
  for(const [value,text] of [["all","Все игры"],["managed","Добавленные через Ember"],["installed","Установленные"],["removed","Удалённые из Ember"]])filter.add(new Option(t(text),value));
  filter.value=selected||"all";filter.setAttribute('aria-label',t("Фильтр библиотеки"));
  refresh.textContent=t(loading?"Обновляем…":"Обновить");refresh.disabled=loading;
  previous.textContent=t("Назад");next.textContent=t("Далее");
 }
 function button(text,action,game,disabled=false){
  const node=document.createElement('button');node.className='btn';node.textContent=t(text);node.dataset.action=action;node.dataset.appid=game.app_id;node.disabled=disabled||loading;
  return node;
 }
 function render(){
  if(lastRemoved&&!games.some(game=>game.app_id===lastRemoved&&game.can_restore))lastRemoved=null;
  label();page.setAttribute('aria-busy',String(loading));status.replaceChildren();
  if(loading){const spinner=document.createElement('span');spinner.className='ember-library-spinner';spinner.setAttribute('aria-hidden','true');status.append(spinner,document.createTextNode(t("Выполняется…")));}
  else if(message)status.textContent=t(message);
  if(!loading&&lastRemoved){const undo=button("Отменить удаление","restore",{app_id:lastRemoved});undo.onclick=()=>act(lastRemoved,'restore');status.append(undo);}
  const query=search.value.trim().toLocaleLowerCase();
  const visible=games.filter(game=>(filter.value==='removed'?game.removed:!game.removed)&&(!query||(game.name+' '+game.app_id).toLocaleLowerCase().includes(query))&&(filter.value!=='managed'||game.managed)&&(filter.value!=='installed'||game.installed));
  current=Math.max(0,Math.min(current,Math.ceil(visible.length/40)-1));
  document.getElementById('ember-library-summary').textContent=t("Игр: {count}",{count:visible.length});
  list.replaceChildren();
  if(!visible.length){const empty=document.createElement('p');empty.className='ember-library-empty';empty.textContent=t(!loaded?"Загружаем библиотеку…":query?"Ничего не найдено":"В этом списке пока нет игр");list.append(empty);}
  for(const game of visible.slice(current*40,current*40+40)){
   const row=document.createElement('article');row.className='ember-library-game';row.dataset.appid=game.app_id;
   const info=document.createElement('div');info.className='ember-library-game-info';
   const name=document.createElement('strong');name.textContent=game.name;name.setAttribute('data-i18n-ignore','');
   const detail=document.createElement('span');detail.textContent='App ID '+game.app_id+' · '+[t(game.installed?"Установлена":"Не установлена"),t(game.removed?"Удалена из Ember":game.managed?"Добавлена через Ember":"Установлена в Steam")].join(' · ');info.append(name,detail);
   const actions=document.createElement('div');actions.className='ember-library-game-actions';
   if(game.removed)actions.append(button("Восстановить","restore",game,!game.can_restore));
   else{
    const main=button(game.installed?"Играть":"Скачать",game.installed?'play':'download',game);main.classList.add('btn-primary');actions.append(main);
    actions.append(button("Установить DLC","dlc",game,!game.installed),button("В Steam","steam",game),button("Магазин","store",game));
    if(game.installed)actions.append(button("Папка игры","folder",game));
    if(game.can_remove)actions.append(button("Удалить из Ember","remove",game,!!window.EmberAdditions?.isPending(game.app_id)));
   }
   row.append(info,actions);list.append(row);
  }
  previous.disabled=loading||current===0;next.disabled=loading||(current+1)*40>=visible.length;
  document.getElementById('ember-library-position').textContent=visible.length?(current+1)+' / '+Math.ceil(visible.length/40):'';
 }
 function supported(){
  if(typeof Bridge.getPy()?.ember_library_refresh==='function')return true;
  message="Перезапустите Ember, чтобы применить обновление библиотеки.";render();return false;
 }
 function load(force=false){
  if(loading||!Bridge.isReady()||!supported())return;
  if(!force&&loaded&&!dirty&&Date.now()-lastLoad<30000)return;
  loading=true;message="";render();Bridge.call('ember_library_refresh');
 }
 function act(id,action){
  if(loading||!supported())return;
  if(action==='dlc'){window.EmberTools?.openGame(id,'dlc_install');return;}
  loading=true;message="";render();Bridge.call('ember_library_action',id,action);
 }
 list.addEventListener('click',event=>{
  const node=event.target.closest('button[data-action]');if(!node||node.disabled)return;
  const id=node.dataset.appid,action=node.dataset.action,game=games.find(item=>item.app_id===id);
  if(action==='remove'){
   Components.showConfirm(t("Удалить из Ember?"),t("Будет удалена регистрация «{name}» в клиентской библиотеке Steam. Файлы игры и сохранения останутся. Действие можно отменить в Ember.",{name:game.name}),()=>act(id,'remove'),null,t("Удалить из Ember"),t("Отмена"));
  }else act(id,action);
 });
 search.addEventListener('input',()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>{current=0;render();},100);});
 filter.onchange=()=>{current=0;render();};refresh.onclick=()=>load(true);
 previous.onclick=()=>{current--;render();};next.onclick=()=>{current++;render();};
 Bridge.on('task_finished',raw=>{
  const result=JSON.parse(raw);
  if(result.task==='download_fastest'){dirty=true;if(page.classList.contains('active')&&!loading)load(true);return;}
  if(result.task!=='ember_library')return;
  loading=false;if(Array.isArray(result.games)){games=result.games;loaded=true;dirty=false;lastLoad=Date.now();}
  message=result.message||(result.success?"":"Не удалось прочитать библиотеку");
  if(result.success&&result.action==='remove')lastRemoved=result.app_id;
  if(result.success&&result.action==='restore')lastRemoved=null;
  render();
 });
 window.addEventListener('ember:rpc-error',event=>{if(!event.detail.method.startsWith('ember_library_'))return;loading=false;message=event.detail.message;render();});
 window.addEventListener('ember:navigate',event=>{if(event.detail==='ember-library')load();});
 window.addEventListener('ember:games',()=>{dirty=true;if(page.classList.contains('active'))load();});
 window.addEventListener('ember:language',render);
 window.addEventListener('ember:resync',()=>{dirty=true;if(page.classList.contains('active'))load(true);});
 render();Bridge.onReady(()=>{if(page.classList.contains('active'))load();});
})();
