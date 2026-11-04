/* Ember — Copyright (C) 2026 Ember contributors.
 * GNU GPL version 3 or later; distributed without any warranty.
 * See LICENSE for the full license and warranty disclaimer.
 */
(() => {
    "use strict";
    if (location.origin !== "https://store.steampowered.com") return;
    window.__emberStore?.dispose();
    const api = window.MILLENNIUM_API;
    const direct = typeof window.__emberStoreBinding === "function";
    if (!api?.ffi && !direct) return;
    const calls = new Map();
    let sequence = Number(window.__emberStoreSequence) || 0;
    const reply = payload => {
        const call = calls.get(payload.call_id);
        if (!call) return;
        clearTimeout(call.timer);calls.delete(payload.call_id);
        if (payload.error) call.reject(new Error(payload.error));else call.resolve(payload.result);
    };
    if (direct) window.__emberStoreReply = reply;
    const ffi = method => !direct && api?.ffi ? api.ffi("app.ember.bridge",method) : (...args) => new Promise((resolve,reject) => {
        const call_id = ++sequence;
        window.__emberStoreSequence = sequence;
        const timer = setTimeout(() => {calls.delete(call_id);reject(new Error("Ember store request timed out"));},15000);
        calls.set(call_id,{resolve,reject,timer});
        window.__emberStoreBinding(JSON.stringify({call_id,method,args}));
    });
    const requestAdd = ffi("request_store_add");
    const readStatus = ffi("get_store_add_status");
    function timed(promise, milliseconds) {
        let timeout;
        return Promise.race([promise,new Promise((_,reject) => {timeout = setTimeout(() => reject(new Error("Ember store request timed out")),milliseconds);})]).finally(() => clearTimeout(timeout));
    }
    let disposed = false, scheduled = false, active = null;
    let language = document.documentElement.lang.toLowerCase().startsWith("en") ? "en" : "ru";
    const states = new Map();
    const labels = {
        add: ["Добавить через Ember", "Add with Ember"],
        opening: ["Открываем Ember…", "Opening Ember…"],
        reconnecting: ["Восстанавливаем связь с Ember…", "Reconnecting to Ember…"],
        opened: ["Открыто в Ember", "Opened in Ember"],
        retry: ["Ember не отвечает. Повторить", "Ember is not responding. Retry"],
        busy: ["Завершите выбор игры в Ember", "Finish selecting the game in Ember"]
    };
    const text = key => labels[key][language === "en" ? 1 : 0];
    function gameId() {
        const match = location.pathname.match(/^\/app\/([1-9]\d{0,9})(?:\/|$)/);
        return match && Number(match[1]) <= 4294967295 ? match[1] : null;
    }
    const style = document.createElement("style");
    style.id = "ember-store-style";
    style.textContent = `#ember-store-action{display:flex;align-items:center;gap:12px;margin:12px 0 16px;color:#b8bcbf;font:13px Arial,sans-serif}#ember-store-add{display:inline-flex;align-items:center;gap:9px;border:0;border-radius:2px;padding:9px 16px;color:#fff;background:linear-gradient(100deg,#06bfff,#2d73ff);font:15px Arial,sans-serif;cursor:pointer}#ember-store-add:hover{background:linear-gradient(100deg,#38caff,#4b8bff)}#ember-store-add:focus-visible{outline:2px solid white;outline-offset:3px}#ember-store-add:disabled{cursor:wait;opacity:.75}#ember-store-add svg{width:16px;height:16px;fill:currentColor}#ember-store-add[aria-busy=true] svg{fill:none;stroke:currentColor;stroke-width:2;animation:ember-store-spin .8s linear infinite}@keyframes ember-store-spin{to{transform:rotate(360deg)}}`;
    document.head.append(style);
    style.textContent += `#ember-store-add svg{width:20px;height:20px;flex:none}#ember-store-add[aria-busy=true] svg{display:none}#ember-store-add[aria-busy=true]::before{content:"";width:16px;height:16px;border:2px solid #ffffff55;border-top-color:#fff;border-radius:50%;animation:ember-store-spin .8s linear infinite}`;
    function refresh() {
        scheduled = false;
        if (disposed) return;
        const id = gameId();
        const anchor = document.querySelector("#game_area_purchase,.game_area_purchase");
        let row = document.getElementById("ember-store-action");
        if (!id || !anchor) { row?.remove(); return; }
        if (row?.dataset.appid !== id) { row?.remove(); row = null; }
        if (!row) {
            row = document.createElement("div");row.id = "ember-store-action";row.dataset.appid = id;
            const button = document.createElement("button");button.id = "ember-store-add";button.type = "button";
            const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");icon.setAttribute("viewBox", "0 0 64 64");icon.setAttribute("aria-hidden", "true");
            const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
            path.setAttribute("d", "M22 16h25l-4 8H29l-3 6h15l-4 8H23l-3 6h22l-4 8H8zM47 10l-1 9 8-4z");
            path.setAttribute("fill", "#fff");icon.append(path);
            const label = document.createElement("span");button.append(icon,label);
            button.addEventListener("click", () => open(id));row.append(button);anchor.before(row);
        }
        const state = states.get(id) || "add", button = row.firstChild;
        if (button.dataset.state === state && button.dataset.language === language) return;
        button.dataset.state = state;button.dataset.language = language;
        const working=state === "opening" || state === "reconnecting";
        button.disabled = working;button.setAttribute("aria-busy", String(working));
        button.lastChild.textContent = text(state);
    }
    async function open(id) {
        if (disposed || gameId() !== id || ["opening","reconnecting"].includes(states.get(id))) return;
        if (active) {states.set(id,"busy");refresh();return;}
        states.set(id,"opening");refresh();
        const name = document.querySelector("#appHubAppName,.apphub_AppName")?.textContent.trim().slice(0,160) || "App " + id;
        const operation = active = {id,deadline:Date.now()+45000,recoveries:0,failures:0};
        try {
            let result;
            for(let attempt=0;attempt<2;attempt++){
                if(disposed || active!==operation)return;
                try {result=await timed(requestAdd(id,name),Math.min(25000,Math.max(1,operation.deadline-Date.now())));break;}
                catch(error){
                    if(disposed || active!==operation || attempt===1 || Date.now()>=operation.deadline)throw error;
                    console.debug("[Ember] Retrying store connection",error);
                    states.set(id,"reconnecting");refresh();
                    await new Promise(resolve=>setTimeout(resolve,750));
                }
            }
            if (disposed || active !== operation) return;
            if (result?.language === "en" || result?.language === "ru") language = result.language;
            if (!result?.success) {states.set(id,result?.error === "busy" ? "busy" : "retry");active = null;refresh();return;}
            operation.request = result.request_id;operation.name=name;operation.deadline = Date.now()+45000;operation.polling = false;
        } catch (error) {
            console.warn("[Ember] Store addition could not be opened",error);
            if (!disposed && active === operation) {states.set(id,"retry");active = null;}
        }
        refresh();
    }
    async function poll() {
        if (disposed) return;
        refresh();
        const operation = active;
        if (!operation?.request || operation.polling) return;
        operation.polling = true;
        try {
            const result = await timed(readStatus(operation.request),4000);
            if (disposed || active !== operation) return;
            if (result?.language === "en" || result?.language === "ru") language = result.language;
            if (result?.state === "opened") {states.set(operation.id,"opened");active = null;}
            else if (result?.state === "expired" && operation.recoveries<1) {operation.failures=2;}
            else if (result?.state === "expired" || Date.now() > operation.deadline) {states.set(operation.id,"retry");active = null;}
            else operation.failures=0;
        } catch (error) {
            console.debug("[Ember] Store handoff status unavailable",error);
            operation.failures++;
            if (Date.now() > operation.deadline && active === operation) {states.set(operation.id,"retry");active = null;}
        } finally {
            if(!disposed && active===operation && operation.failures>=2 && operation.recoveries<1){
                operation.recoveries++;states.set(operation.id,"reconnecting");refresh();
                try{
                    const result=await timed(requestAdd(operation.id,operation.name),25000);
                    if(!disposed && active===operation && result?.success){operation.request=result.request_id;operation.failures=0;}
                }catch(error){console.debug("[Ember] Store recovery unavailable",error);}
            }
            operation.polling = false;refresh();
        }
    }
    const observer = new MutationObserver(() => {if (!scheduled) {scheduled = true;queueMicrotask(refresh);}});
    observer.observe(document.documentElement,{childList:true,subtree:true});
    const timer = setInterval(poll,1000);
    window.__emberStore = {dispose() {
        disposed = true;clearInterval(timer);observer.disconnect();style.remove();document.getElementById("ember-store-action")?.remove();
        for (const call of calls.values()) {clearTimeout(call.timer);call.reject(new Error("Ember store adapter unloaded"));}calls.clear();
        if (window.__emberStoreReply === reply) delete window.__emberStoreReply;
    }};
    refresh();
})();
