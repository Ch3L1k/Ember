/* Ember — Copyright (C) 2026 Ember contributors.
 * SPDX-License-Identifier: GPL-3.0-or-later */
(() => {
    'use strict';
    const t = (...args) => I18n.t(...args);
    const panel = document.getElementById('ember-api-keys');
    panel.innerHTML = '<h2 id="ember-api-keys-title"></h2><p class="ember-api-description"></p><div class="ember-api-list"></div><p class="ember-api-load-status" role="status"></p><button class="btn ember-api-retry" hidden></button>';
    const list = panel.querySelector('.ember-api-list');
    const loading = panel.querySelector('.ember-api-load-status');
    const retry = panel.querySelector('.ember-api-retry');
    const rows = new Map();
    let loadingKeys = false;
    async function call(method, args = []) {
        const response = await EmberTransport.request('/api/call', {method, args});
        return JSON.parse(response.result);
    }
    function renderRow(row) {
        const {data, input, save, remove, show, state, status} = row;
        row.description.textContent = t(data.description);
        input.placeholder = t(data.configured ? 'Введите новый ключ для замены' : 'Введите API-ключ');
        save.textContent = t(state.busy === 'save' ? 'Сохраняем…' : 'Сохранить');
        remove.textContent = t(state.busy === 'remove' ? 'Удаляем…' : 'Удалить');
        show.textContent = t(input.type === 'password' ? 'Показать' : 'Скрыть');
        show.setAttribute('aria-label', t('Показать или скрыть введённый ключ {provider}', {provider: data.name}));
        save.disabled = !!state.busy || !input.value.trim();
        remove.disabled = !!state.busy || !data.configured;
        show.disabled = !!state.busy || !input.value;
        input.disabled = !!state.busy;
        row.form.setAttribute('aria-busy', String(!!state.busy));
        status.textContent = t(state.message || (data.configured ? 'Ключ сохранён' : 'Ключ не указан'));
        status.classList.toggle('ember-api-error', !!state.error);
    }
    function render() {
        panel.querySelector('h2').textContent = t('API-ключи');
        panel.querySelector('.ember-api-description').textContent = t('Укажите ключи используемых сервисов. Сохранение не проверяет их действительность у провайдера.');
        retry.textContent = t('Повторить');
        for (const row of rows.values()) renderRow(row);
    }
    async function change(row, deleting) {
        if (row.state.busy) return;
        const value = deleting ? '' : row.input.value.trim();
        if (!deleting && !value) return;
        row.state.busy = deleting ? 'remove' : 'save';
        row.state.message = deleting ? 'Удаляем…' : 'Сохраняем…';
        row.state.error = false; renderRow(row);
        try {
            const result = await call('ember_set_api_key', [row.data.id, value]);
            row.data.configured = result.configured;
            row.input.value = ''; row.input.type = 'password';
            row.state.message = deleting ? 'Ключ удалён' : 'Ключ сохранён';
            window._updateDownloadSourceHint?.();
        } catch (_) {
            console.debug('[Ember] Provider setting could not be saved');
            row.state.error = true;
            row.state.message = 'Не удалось сохранить ключ. Повторите попытку.';
        } finally { row.state.busy = null; renderRow(row); }
    }
    function addRow(data) {
        const form = document.createElement('form');
        form.className = 'ember-api-row ember-preference';
        form.innerHTML = '<div><label></label><small></small></div><div><div class="ember-api-entry"><input type="password" autocomplete="off" spellcheck="false" maxlength="4096"><button class="btn" type="button"></button></div><div class="ember-api-controls"><span role="status"></span><button class="btn btn-primary" type="submit"></button><button class="btn" type="button"></button></div></div>';
        const input = form.querySelector('input'); input.id = 'ember-key-' + data.id;
        const label = form.querySelector('label'); label.htmlFor = input.id; label.textContent = data.name;
        const [show, save, remove] = form.querySelectorAll('button');
        const row = {form, data, input, show, save, remove, description: form.querySelector('small'), status: form.querySelector('[role="status"]'), state: {busy: null, message: '', error: false}};
        input.addEventListener('input', () => { row.state.message = ''; row.state.error = false; renderRow(row); });
        show.onclick = () => { input.type = input.type === 'password' ? 'text' : 'password'; renderRow(row); };
        form.onsubmit = event => { event.preventDefault(); change(row, false); };
        remove.onclick = () => change(row, true);
        rows.set(data.id, row); list.append(form); renderRow(row);
    }
    async function load() {
        if (loadingKeys) return;
        loadingKeys = true; retry.hidden = true; loading.textContent = t('Загружаем настройки…');
        try {
            const data = await call('ember_get_api_keys');
            for (const key of data) {
                if (rows.has(key.id)) rows.get(key.id).data = key;
                else addRow(key);
            }
            loading.textContent = ''; render();
        } catch (_) {
            console.debug('[Ember] Provider settings unavailable');
            loading.textContent = t('Не удалось загрузить настройки ключей.'); retry.hidden = false;
        } finally { loadingKeys = false; }
    }
    retry.onclick = load;
    Bridge.onReady(load);
    Bridge.on('task_finished', raw => {
        const result = JSON.parse(raw);
        if (result.task !== 'ember_api_key') return;
        const row = rows.get(result.id);
        if (row) { row.data.configured = result.configured; if (!row.state.busy) row.state.message = ''; renderRow(row); }
    });
    window.addEventListener('ember:resync', load);
    window.addEventListener('ember:language', render);
    render();
})();
