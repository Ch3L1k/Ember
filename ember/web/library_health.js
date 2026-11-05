/* Ember — Copyright (C) 2026 Ember contributors.
 * SPDX-License-Identifier: GPL-3.0-or-later */
(() => {
    'use strict';
    const t = (...args) => I18n.t(...args);
    const select = document.getElementById('ember-tool-game');
    const panel = document.createElement('section');
    panel.className = 'ember-tool-panel';
    panel.innerHTML = '<h2></h2><p></p><div class="ember-tool-actions"><button class="btn btn-primary" disabled></button><button class="btn" disabled></button></div><div role="status" style="margin-top:16px;line-height:1.6;overflow-wrap:anywhere"></div>';
    document.querySelector('#page-ember-tools .ember-tool-panel').before(panel);
    const [check, fix] = panel.querySelectorAll('button');
    const report = panel.querySelector('[role="status"]');
    const states = new Map(), pending = new Map();
    const actions = ['inspect_library', 'repair_library'];
    function render() {
        const id = select.value, state = states.get(id), action = pending.get(id);
        panel.querySelector('h2').textContent = t('Карточка игры в Steam');
        panel.querySelector('p').textContent = t('Проверка времени в игре, последнего запуска и списка достижений. Обновление данных из Steam и восстановление известных настроек интеграции.');
        check.disabled = !id || !!action;
        fix.disabled = !id || !!action || !state?.success || !state?.repairable;
        check.textContent = t(action === actions[0] ? 'Проверяем…' : 'Проверить библиотеку');
        fix.textContent = t(action === actions[1] ? 'Исправляем…' : 'Исправить и обновить');
        panel.setAttribute('aria-busy', String(!!action));
        report.replaceChildren();
        if (action) { report.textContent = t('Получаем данные Steam…'); return; }
        if (!state) { report.textContent = t('Выберите игру и нажмите «Проверить библиотеку».'); return; }
        const rows = [...(state.checks || [])];
        if (state.statistics) {
            const s = state.statistics;
            rows.push(t('Время по данным Steam: {minutes} мин.', {minutes: s.minutes}));
            rows.push(t('Достижения: {achieved} из {total}.', {achieved: s.achieved, total: s.total}));
            if (s.last_played > 0) rows.push(t('Последний запуск: {date}', {date: new Date(s.last_played * 1000).toLocaleString()}));
        }
        rows.push(state.message);
        if (state.backup) rows.push(t('Резервная копия: {path}', {path: state.backup}));
        for (const text of rows.filter(Boolean)) {
            const row = document.createElement('div'); row.textContent = t(text); report.append(row);
        }
    }
    function run(action) {
        const id = select.value;
        if (!id || pending.has(id)) return;
        pending.set(id, action); render(); Bridge.call('ember_tool_action', id, action);
    }
    check.onclick = () => run(actions[0]); fix.onclick = () => run(actions[1]);
    select.addEventListener('change', render);
    Bridge.on('task_finished', raw => {
        const result = JSON.parse(raw);
        if (result.task !== 'ember_tool' || !actions.includes(result.action)) return;
        const id = String(result.app_id); pending.delete(id); states.set(id, result); render();
    });
    window.addEventListener('ember:rpc-error', event => {
        const value = event.detail;
        if (value.method !== 'ember_tool_action' || !actions.includes(value.args[1])) return;
        const id = String(value.args[0]); pending.delete(id);
        states.set(id, {success: false, message: value.message}); render();
    });
    window.addEventListener('ember:games', render);
    window.addEventListener('ember:language', render);
    render();
})();
