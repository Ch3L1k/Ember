/* Ember — Copyright (C) 2026 Ember contributors.
 * GNU GPL version 3 or later; distributed without any warranty.
 * See LICENSE for the full license and warranty disclaimer.
 */
(() => {
    "use strict";
    const id = "app.ember.bridge";
    window.__emberMillennium?.dispose();
    const api = window.MILLENNIUM_API;
    const React = window.SP_REACT;
    const h = React.createElement;
    const route = "/ember";
    const readConnection = api.ffi(id, "get_connection");
    const startBackend = api.ffi(id, "start_backend");
    const subscribers = new Set();
    const menus = new Map();
    let current = null, disposed = false, busy = false, lastOpen = "";
    let starting = false, lastStart = 0, startAttempts = 0;
    let language = "ru";
    let lastAdd = "", pageMounted = false, lastNavigation = 0;
    const english = {
        "Нет связи с Ember. Повторите подключение.": "Cannot connect to Ember. Try reconnecting.",
        "Некорректный адрес Ember": "Invalid Ember address",
        "Ember остановлен. Повторите подключение.": "Ember has stopped. Try reconnecting.",
        "Не удалось проверить Ember": "Could not verify Ember",
        "Запуск Ember…": "Starting Ember…",
        "Подключиться повторно": "Reconnect"
    };
    const text = value => language === "en" ? english[value] || value : value;
    const navigate = () => api.Navigation.Navigate(route);
    function timed(promise, milliseconds) {
        let timeout;
        return Promise.race([promise,new Promise((_,reject) => {timeout=setTimeout(()=>reject(new Error("Ember connection timed out")),milliseconds);})]).finally(()=>clearTimeout(timeout));
    }
    async function recover(force=false) {
        if(disposed || starting || (!force && (startAttempts>=3 || Date.now()-lastStart<10000)))return;
        starting=true;lastStart=Date.now();startAttempts++;
        console.debug("[Ember] Recovering backend connection",startAttempts);
        try {await timed(startBackend(),25000);}
        catch(error){console.warn("[Ember] Backend recovery failed",error);}
        finally {starting=false;if(!disposed)poll();}
    }

    function attachMenu(context) {
        if (disposed || context.m_strTitle !== "Steam Root Menu") return;
        const win = context.window || context.m_popup?.window;
        if (!win?.document || menus.has(win)) return;
        const doc = win.document;
        function update() {
            if (disposed || doc.getElementById("ember-steam-menuitem")) return;
            const items = [...doc.querySelectorAll('[role="menuitem"]')];
            if (items.length < 3) return;
            const reference = items.find(item => item.getAttribute("aria-disabled") !== "true" && !item.hasAttribute("disabled"));
            if (!reference) return;
            const item = doc.createElement(reference.tagName);
            item.id = "ember-steam-menuitem";
            item.className = reference.className;
            item.setAttribute("role", "menuitem");
            item.setAttribute("aria-disabled", "false");
            item.tabIndex = 0;
            item.textContent = "Ember";
            function activate() {
                navigate();
                win.dispatchEvent(new win.KeyboardEvent("keydown", {key: "Escape", code: "Escape", bubbles: true}));
            }
            item.addEventListener("click", activate);
            item.addEventListener("keydown", event => {
                if (event.key === "Enter" || event.key === " ") { event.preventDefault(); activate(); }
            });
            items.at(-2).before(item);
        }
        const observer = new win.MutationObserver(update);
        observer.observe(doc.documentElement, {childList: true, subtree: true});
        menus.set(win, observer);
        update();
    }

    async function poll() {
        if (disposed || busy) return;
        busy = true;
        try {
            const connection = await timed(readConnection(),5000);
            if (disposed) return;
            if (connection.origin && !/^http:\/\/127\.0\.0\.1:\d+$/.test(connection.origin)) throw new Error("Invalid Ember origin");
            current = connection;
            if(connection.origin){startAttempts=0;}
            else recover();
            if (connection.language === "en" || connection.language === "ru") language = connection.language;
            const addition = connection.add_request;
            if (addition && typeof addition.request_id === "string" && /^[1-9]\d{0,9}$/.test(addition.app_id) && Number(addition.app_id) <= 4294967295 && typeof addition.name === "string" && addition.name.length <= 512 && Math.abs(Date.now()/1000 - addition.created) < 60) {
                if (lastAdd !== addition.request_id || (!pageMounted && Date.now()-lastNavigation>3000)) {
                    lastAdd = addition.request_id;lastNavigation = Date.now();navigate();
                    console.debug("[Ember] Opening store source picker in Steam");
                }
            }
            if (connection.open_request && connection.open_request !== lastOpen && Number(connection.open_request) / 1e6 > Date.now() - 60000) {
                lastOpen = connection.open_request;
                navigate();
            }
            subscribers.forEach(update => update(connection));
        } catch (error) {
            console.warn("[Ember] Adapter connection failed", error);
            current = {error: "Нет связи с Ember. Повторите подключение."};
            subscribers.forEach(update => update(current));
            recover();
        } finally { busy = false; }
    }

    function EmberPage() {
        const [connection, update] = React.useState(current);
        React.useEffect(() => { pageMounted = true;subscribers.add(update);poll();return () => {pageMounted = false;subscribers.delete(update);}; }, []);
        const style = {position: "absolute", inset: 0, width: "100%", height: "100%", border: 0, background: "#171d25"};
        if (connection?.origin && connection?.token) {
            return h("iframe", {key: connection.pid, title: "Ember", src: connection.origin + "/?surface=steam#token=" + encodeURIComponent(connection.token), style});
        }
        return h("div", {style: {...style, padding: "36px 24px", boxSizing: "border-box", color: "#dcdedf", font: "14px Arial"}},
            h("h1", {style: {fontSize: 23, color: "#fff"}}, "Ember"),
            h("p", null, text(connection?.error || "Запуск Ember…")),
            h("button", {onClick: () => recover(true), style: {background: "#292e36", color: "white", border: 0, padding: "10px 16px", cursor: "pointer"}}, text("Подключиться повторно")));
    }

    api.routerHook.addRoute(route, EmberPage, {exact: false});
    api.Millennium.AddWindowCreateHook(attachMenu);
    const timer = setInterval(poll, 2000);
    poll();
    const state = window.__emberMillennium = {
        route, get connected() { return !!current?.origin; },
        dispose() {
            disposed = true;
            clearInterval(timer);
            api.routerHook.removeRoute(route);
            for (const [win, observer] of menus) { observer.disconnect(); win.document.getElementById("ember-steam-menuitem")?.remove(); }
            menus.clear(); subscribers.clear();
        }
    };
    (window.PLUGIN_LIST ||= {})[id] = {onDismount: state.dispose};
    window.__millennium_plugin_console_binding__?.(JSON.stringify({plugin: id, level: "info", source: "frontend", message: "Ember route /ember and Steam menu hook registered; store handoff v2"}));
    window.MILLENNIUM_BACKEND_IPC?.postMessage(1, {pluginName: id});
})();
