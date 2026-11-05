# Ember — Copyright (C) 2026 Ember contributors.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Provider key settings shared by the preferences page and add-game dialog."""
import logging
import time

from sff.core.storage.settings import get_setting, set_setting, clear_setting
from sff.core.structs import Settings

logger = logging.getLogger(__name__)
_KEYS = (
    (Settings.HUBCAP_KEY, 'Hubcap', 'Источник данных для добавления игр.'),
    (Settings.RYUU_KEY, 'Ryuu Reseller', 'Ключ реселлера Ryuu. Используется отдельно от обычного API-ключа.'),
    (Settings.RYUU_API_KEY, 'Ryuu API', 'Обычный API-ключ Ryuu.'),
    (Settings.DEPOTBOX_KEY, 'DepotBox', 'Источник данных для добавления игр.'),
    (Settings.STEAM_WEB_API_KEY, 'Steam Web API', 'Запросы каталога Steam. Не нужен для входа в аккаунт.'),
    (Settings.MANIFESTHUB_API_KEY, 'ManifestHub', 'Загрузка манифестов. Временный ключ действует до 24 часов.'),
)
_REJECTED = {
    Settings.HUBCAP_KEY: Settings.HUBCAP_KEY_DEAD,
    Settings.RYUU_KEY: Settings.RYUU_KEY_DEAD,
    Settings.RYUU_API_KEY: Settings.RYUU_KEY_DEAD,
    Settings.DEPOTBOX_KEY: Settings.DEPOTBOX_KEY_DEAD,
}


def snapshot():
    return [{'id': setting.key_name, 'name': name, 'description': description,
             'configured': bool(get_setting(setting))}
            for setting, name, description in _KEYS]


def save(bridge, key, value):
    setting = next((setting for setting, _, _ in _KEYS if setting.key_name == key), None)
    if setting is None or not isinstance(value, str):
        raise ValueError('Неизвестный API-ключ.')
    value = value.strip()
    if len(value) > 4096 or any(ord(char) < 33 or ord(char) == 127 for char in value):
        raise ValueError('Ключ не должен содержать пробелы или переносы строк.')
    try:
        if value:
            set_setting(setting, value)
        else:
            clear_setting(setting)
        if (get_setting(setting) or '') != value:
            raise RuntimeError('Setting verification failed')
        if setting in _REJECTED:
            clear_setting(_REJECTED[setting])
        if setting == Settings.MANIFESTHUB_API_KEY:
            from sff.manifest import manifesthub_key
            if value:
                set_setting(Settings.MANIFESTHUB_KEY_EXPIRY, str(time.time() + manifesthub_key._EXPIRY_SECONDS))
            else:
                clear_setting(Settings.MANIFESTHUB_KEY_EXPIRY)
            manifesthub_key._skipped_this_session = False
    except Exception as error:
        logger.warning('Could not save provider setting %s (%s)', key, type(error).__name__)
        raise RuntimeError('Не удалось сохранить ключ. Повторите попытку.') from None
    if setting == Settings.HUBCAP_KEY:
        bridge._api_key = value or None
        bridge._store_client = None
        bridge._hubcap_unavailable = not bool(value)
    logger.info('Provider setting %s %s', key, 'saved' if value else 'removed')
    return {'id': key, 'configured': bool(value)}
