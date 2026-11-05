/* Ember — Copyright (C) 2026 Ember contributors.
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
(() => {
    "use strict";
    function shortSession(details, overview, managed, now = Date.now() / 1000) {
        if (!details || !overview || !managed.includes(String(details.unAppID)) ||
            Number(overview.appid) !== details.unAppID || details.nPlaytimeForever !== 0 ||
            !(overview.rt_last_time_locally_played > 0)) return null;
        const last = details.rtLastTimePlayed;
        return Number.isFinite(last) && last >= 31536000 && last <= now + 300 ? last : null;
    }

    function create(config) {
        const classes = config.classes || {};
        const marker = 'data-ember-short-session';
        let warned = false;
        function propsFor(element) {
            const key = Object.keys(element).find(key => key.startsWith('__reactFiber$'));
            let fiber = key && element[key];
            for (let depth = 0; fiber && depth < 20; depth++, fiber = fiber.return) {
                const props = fiber.memoizedProps;
                if (props?.details && props?.overview) return props;
            }
            return null;
        }
        function block(kind, label, value) {
            const element = document.createElement('div');
            element.className = [classes.GameStat, classes[kind]].filter(Boolean).join(' ');
            element.setAttribute(marker, kind);
            const right = document.createElement('div');
            right.className = classes.GameStatRight || '';
            const title = document.createElement('div');
            title.className = classes.PlayBarLabel || '';
            title.textContent = label;
            const content = document.createElement('div');
            content.className = classes.PlayBarDetailLabel || '';
            content.textContent = value;
            right.append(title, content);
            if (kind === 'Playtime') {
                const icon = document.createElement('div');
                icon.className = [classes.GameStatIcon, classes.PlaytimeIcon].filter(Boolean).join(' ');
                icon.setAttribute('aria-hidden', 'true');
                icon.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" class="SVGIcon_Button SVGIcon_PlayTime" width="256" height="256" viewBox="0 0 256 256"><polyline fill="none" stroke="#000000" stroke-width="16" stroke-linecap="round" stroke-linejoin="round" stroke-miterlimit="10" points="85.5,149.167 128,128 128,55.167"/><path fill="none" stroke="#000000" stroke-width="16" stroke-linecap="round" stroke-linejoin="round" stroke-miterlimit="10" d="M128,17.5c61.027,0,110.5,49.473,110.5,110.5S189.027,238.5,128,238.5S17.5,189.027,17.5,128"/><circle stroke="#000000" stroke-width="7" stroke-linecap="round" stroke-linejoin="round" stroke-miterlimit="10" cx="26.448" cy="85.833" r="5.5"/><circle stroke="#000000" stroke-width="7" stroke-linecap="round" stroke-linejoin="round" stroke-miterlimit="10" cx="50.167" cy="50.5" r="5.5"/><circle stroke="#000000" stroke-width="7" stroke-linecap="round" stroke-linejoin="round" stroke-miterlimit="10" cx="86" cy="26.667" r="5.5"/></svg>';
                element.append(icon);
            }
            element.append(right);
            return element;
        }
        function refresh() {
            if (!classes.GameStatsSection) return;
            try {
                const russian = new URLSearchParams(location.search).get('LANGUAGE') === 'russian';
                for (const section of document.getElementsByClassName(classes.GameStatsSection)) {
                    const props = propsFor(section);
                    const last = shortSession(props?.details, props?.overview, config.libraryApps || []);
                    const signature = last ? `${props.details.unAppID}:${last}:${russian}` : '';
                    const previous = [...section.querySelectorAll(`[${marker}]`)];
                    if (signature && section.dataset.emberSession === signature && previous.length === 2) continue;
                    previous.forEach(element => element.remove());
                    section.dataset.emberSession = signature;
                    if (!last) continue;
                    const date = new Date(last * 1000);
                    const locale = russian ? 'ru-RU' : 'en-US';
                    const text = date.toDateString() === new Date().toDateString() ? (russian ? 'Сегодня' : 'Today') : date.toLocaleDateString(locale, {day:'numeric', month:'short'});
                    const played = block('LastPlayed', russian ? 'Последний запуск' : 'Last played', text);
                    played.title = date.toLocaleString(locale);
                    const time = block('Playtime', russian ? 'Время в игре' : 'Play time', russian ? 'Меньше минуты' : 'Less than a minute');
                    const achievements = [...section.children].find(element => classes.MiniAchievements && element.classList.contains(classes.MiniAchievements));
                    section.insertBefore(played, achievements || null);
                    section.insertBefore(time, achievements || null);
                }
            } catch (error) {
                if (!warned) console.warn('Ember: short-session display unavailable', error);
                warned = true;
            }
        }
        function dispose() {
            document.querySelectorAll(`[${marker}]`).forEach(element => element.remove());
            document.querySelectorAll('[data-ember-session]').forEach(element => delete element.dataset.emberSession);
        }
        return {refresh, dispose};
    }
    if (typeof module !== 'undefined' && module.exports) module.exports = {shortSession, create};
    else window.__emberLibraryStatsCreate = create;
})();
