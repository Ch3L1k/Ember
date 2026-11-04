/* Ember — Copyright (C) 2026 Ember contributors.
 * GNU GPL version 3 or later; distributed without any warranty.
 * See LICENSE for the full license and warranty disclaimer.
 */
(() => {
    "use strict";
    if (window.__emberSteam) return window.__emberSteam.refresh();
    const config = window.__EMBER_CONFIG__;
    const state = { observer: null, panel: null, disposed: false };
    const navigationStyle = document.createElement("style");
    navigationStyle.id = "ember-steam-navigation-style";
    if (config.embedded && config.classes?.SuperNavBar && config.classes?.SuperNavButton) {
        const button = 'html[data-ember-open="true"] .' + CSS.escape(config.classes.SuperNavBar) + ' .' + CSS.escape(config.classes.SuperNavButton);
        navigationStyle.textContent = button + '{color:#dcdedf!important}' + button + '::after{display:none!important}';
        document.head.append(navigationStyle);
    }

    function geometry() {
        if (!config.embedded || !state.panel) return;
        const find = key => config.classes?.[key] ? document.getElementsByClassName(config.classes[key])[0] : null;
        const header = find("SuperNavBar")?.getBoundingClientRect();
        const footer = find("BottomBarContainer")?.getBoundingClientRect();
        const content = find("LocalContentContainer")?.getBoundingClientRect();
        const top = Math.max(content?.height > 100 ? content.top : 0, header?.height > 0 ? header.bottom : 66) + 12;
        const bottom = footer?.height > 0 ? innerHeight - footer.top : 48;
        state.panel.style.top = Math.round(top) + "px";
        state.panel.style.bottom = Math.round(bottom) + "px";
        state.panel.style.left = Math.round(content?.left || 0) + "px";
        state.panel.style.right = Math.round(content?.width > 0 ? innerWidth - content.right : 0) + "px";
    }

    function navigate(event) {
        if (!config.embedded || !state.panel || state.panel.hidden || state.panel.contains(event.target)) return;
        for (const key of ["SuperNavBar", "BottomBarContainer"]) {
            const name = config.classes?.[key];
            if (name && event.target.closest("." + CSS.escape(name))) { close(); break; }
        }
    }

    function close() {
        if (state.panel) { state.panel.hidden = true; state.panel.style.display = "none"; }
        document.documentElement.removeAttribute("data-ember-open");
    }

    function open() {
        if (config.nativeWindow) {
            window.__emberOpenPanel("open");
            return;
        }
        if (!state.panel) {
            const panel = document.createElement("section");
            panel.id = "ember-steam-panel";
            panel.setAttribute("aria-label", "Ember");
            panel.style.cssText = "position:fixed;inset:76px 12px 12px;z-index:2147483000;background:#171d25;border:1px solid #434953;border-radius:3px;box-shadow:0 16px 60px #0009;display:flex;flex-direction:column;overflow:hidden;color:#dcdedf;font:14px Arial,sans-serif";
            if (config.embedded) panel.style.cssText = "position:fixed;inset:66px 0 48px;z-index:1000;background:#171d25;display:flex;overflow:hidden;border:0;border-radius:0;box-shadow:none;color:#dcdedf;font:14px Arial,sans-serif";
            const bar = document.createElement("header");
            bar.style.cssText = "display:flex;align-items:center;gap:12px;height:40px;min-height:40px;padding:0 16px;background:#1d2028;border-bottom:1px solid #ffffff13";
            const title = document.createElement("strong");
            title.textContent = "EMBER";
            title.style.cssText = "color:#dcdedf;letter-spacing:1px";
            const hint = document.createElement("span");
            hint.textContent = "Игры · Инструменты · Сообщество";
            hint.style.cssText = "opacity:.55;font-size:12px;flex:1";
            const button = document.createElement("button");
            button.textContent = "Закрыть ×";
            button.title = "Закрыть Ember";
            button.style.cssText = "border:0;background:transparent;color:#ddd;padding:8px 4px;cursor:pointer";
            button.addEventListener("click", close);
            bar.append(title, hint, button);
            const frame = document.createElement("iframe");
            frame.title = "Ember";
            frame.src = config.origin + (config.embedded ? "/?surface=steam#token=" : "/#token=") + encodeURIComponent(config.token);
            frame.style.cssText = "border:0;flex:1;width:100%;min-height:0;background:#11151d";
            if (config.embedded) frame.style.height = "100%";
            if (!config.embedded) panel.append(bar);
            panel.append(frame);
            document.body.append(panel);
            state.panel = panel;
        }
        state.panel.hidden = false;
        state.panel.style.display = "flex";
        if (config.embedded) document.documentElement.setAttribute("data-ember-open", "true");
        geometry();
    }

    function refresh() {
        geometry();
        if (state.disposed || document.title !== "Steam Root Menu") return;
        if (document.getElementById("ember-steam-menuitem")) return;
        const items = [...document.querySelectorAll('[role="menuitem"]')];
        if (items.length < 3) return;
        const sample = items.find(candidate => candidate.getAttribute("aria-disabled") !== "true" && !candidate.hasAttribute("disabled")) || items[0];
        const item = document.createElement(sample.tagName);
        item.id = "ember-steam-menuitem";
        item.className = sample.className;
        item.setAttribute("role", "menuitem");
        item.tabIndex = 0;
        item.textContent = "Ember";
        item.setAttribute("aria-disabled", "false");
        const activate = () => {
            if (typeof window.__emberOpenPanel === "function") window.__emberOpenPanel("open");
            window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", code: "Escape", bubbles: true }));
        };
        item.addEventListener("click", activate);
        item.addEventListener("keydown", event => {
            if (event.key === "Enter" || event.key === " ") { event.preventDefault(); activate(); }
        });
        const settings = items.at(-2);
        settings.parentNode.insertBefore(item, settings);
        const container = document.querySelector("#popup_target > div");
        if (container) container.style.overflowY = "auto";
    }

    state.observer = new MutationObserver(refresh);
    state.observer.observe(document.documentElement, { childList: true, subtree: true });
    window.addEventListener("resize", geometry);
    document.addEventListener("click", navigate, true);
    window.__emberSteam = {
        open, close, refresh,
        dispose() {
            state.disposed = true;
            state.observer.disconnect();
            window.removeEventListener("resize", geometry);
            document.removeEventListener("click", navigate, true);
            document.getElementById("ember-steam-menuitem")?.remove();
            state.panel?.remove();
            navigationStyle.remove();
            document.documentElement.removeAttribute("data-ember-open");
            delete window.__emberSteam;
        }
    };
    refresh();
})();
