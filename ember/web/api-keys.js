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
        row.edit.textContent = t(data.configured ? 'Изменить' : 'Добавить ключ');
        row.edit.disabled = !!state.busy;
        row.edit.setAttribute('aria-expanded', String(state.open));
        row.editor.hidden = !state.open;
        row.form.classList.toggle('is-open', state.open);
        row.badge.textContent = t(data.configured ? 'Сохранён' : 'Не указан');
        row.badge.classList.toggle('is-saved', data.configured);
        row.cancel.textContent = t('Отмена');
        row.cancel.disabled = !!state.busy;
        row.fieldLabel.textContent = t('API-ключ');
        remove.hidden = !data.configured;
        status.hidden = !state.message;
        show.title = t(input.type === 'password' ? 'Показать' : 'Скрыть');
        show.setAttribute('aria-pressed', String(input.type !== 'password'));
        input.placeholder = t(data.configured ? 'Введите новый ключ для замены' : 'Введите API-ключ');
        save.textContent = t(state.busy === 'save' ? 'Сохраняем…' : 'Сохранить');
        remove.textContent = t(state.busy === 'remove' ? 'Удаляем…' : 'Удалить');
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
        panel.querySelector('.ember-api-description').textContent = t('Подключите нужные сервисы. Остальные поля можно оставить пустыми.');
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
            row.state.open = false; row.edit.focus({preventScroll: true});
            window._updateDownloadSourceHint?.();
        } catch (_) {
            console.debug('[Ember] Provider setting could not be saved');
            row.state.error = true;
            row.state.message = 'Не удалось сохранить ключ. Повторите попытку.';
        } finally { row.state.busy = null; renderRow(row); }
    }
    function addRow(data) {
        const form = document.createElement('form');
        form.className = 'ember-api-row';
        form.innerHTML = `<div class="ember-api-summary">
            <span class="ember-api-symbol" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="9" r="5"/><path d="m12 12 9 9m-3-3 3-3m-6 0 3-3"/></svg></span>
            <div class="ember-api-info"><strong></strong><small></small></div>
            <span class="ember-api-badge"></span><button class="btn ember-api-edit" type="button"></button>
        </div>
        <div class="ember-api-editor" hidden><label class="ember-api-label"></label>
            <div class="ember-api-entry"><input type="password" autocomplete="off" spellcheck="false" maxlength="4096"><button class="btn ember-api-show" type="button"><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg></button></div>
            <div class="ember-api-controls"><button class="btn ember-api-remove" type="button"></button><span class="ember-api-controls-spacer"></span><button class="btn ember-api-cancel" type="button"></button><button class="btn btn-primary ember-api-save" type="submit"></button></div>
        </div><div class="ember-api-feedback" role="status" hidden></div>`;
        const input = form.querySelector('input'); input.id = 'ember-key-' + data.id;
        const fieldLabel = form.querySelector('label'); fieldLabel.htmlFor = input.id;
        form.querySelector('strong').textContent = data.name;
        const find = name => form.querySelector('.ember-api-' + name);
        const row = {form, data, input, fieldLabel, show: find('show'), save: find('save'), remove: find('remove'), edit: find('edit'), cancel: find('cancel'), editor: find('editor'), badge: find('badge'), description: form.querySelector('small'), status: find('feedback'), state: {busy: null, open: false, message: '', error: false}};
        row.editor.id = 'ember-key-editor-' + data.id;
        row.edit.setAttribute('aria-controls', row.editor.id);
        input.addEventListener('input', () => { row.state.message = ''; row.state.error = false; renderRow(row); });
        row.show.onclick = () => { input.type = input.type === 'password' ? 'text' : 'password'; renderRow(row); input.focus(); };
        row.edit.onclick = () => {
            row.state.open = !row.state.open;
            input.type = 'password';
            renderRow(row);
            if (row.state.open) input.focus();
        };
        function cancel() {
            if (row.state.busy) return;
            row.state.open = false; row.state.message = ''; row.state.error = false;
            input.value = ''; input.type = 'password'; renderRow(row); row.edit.focus({preventScroll: true});
        }
        row.cancel.onclick = cancel;
        row.editor.addEventListener('keydown', event => {
            if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); cancel(); }
        });
        form.onsubmit = event => { event.preventDefault(); change(row, false); };
        row.remove.onclick = () => change(row, true);
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
