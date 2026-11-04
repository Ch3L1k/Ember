# Ember — Copyright (C) 2026 Ember contributors.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Match registration content to Steam's selected execution platform."""
import json
import logging
import os
from pathlib import Path
import time
import urllib.request

logger = logging.getLogger(__name__)


def required_platform(info, depot_ids):
    depots = info.get('depots', {})
    if not isinstance(depots, dict) or not depots:
        raise ValueError('Не удалось проверить платформу файлов игры. Повторите добавление позже.')
    declared = set(str(info.get('common', {}).get('oslist', '')).split(','))
    platforms = set()
    for depot_id, depot in depots.items():
        if str(depot_id) not in depot_ids or not isinstance(depot, dict):
            continue
        if depot.get('depotfromapp') or not depot.get('manifests'):
            continue
        oslist = str(depot.get('config', {}).get('oslist', ''))
        platforms.update(oslist.split(',') if oslist else declared)
    if {'linux', 'windows'} <= platforms:
        return 'both'
    if 'linux' in platforms:
        return 'linux'
    if 'windows' in platforms:
        return 'windows'
    raise ValueError('Источник не содержит проверяемых файлов игры для Linux или Windows. Выберите другой источник.')


def _steam_client():
    from ember.cdp import CDPClient
    for raw in os.environ.get('EMBER_CDP_PORTS', '8080').split(','):
        try:
            port = int(raw)
            if not 0 < port < 65536:
                continue
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/json/list', timeout=2) as response:
                targets = json.load(response)
            target = next(t for t in targets if t.get('title') == 'SharedJSContext'
                          and t.get('url', '').startswith('https://steamloopback.host/'))
            return CDPClient(target['webSocketDebuggerUrl'], lambda: None)
        except Exception:
            logger.debug('Compatibility target unavailable on port %s', raw, exc_info=True)
    raise ValueError('Не удалось подключиться к настройкам совместимости Steam. Откройте Steam и повторите добавление.')


def _evaluate(client, expression):
    result = client.call('Runtime.evaluate', {'expression': expression, 'awaitPromise': True, 'returnByValue': True}, timeout=8)
    if result.get('exceptionDetails'):
        raise RuntimeError('Steam не подтвердил настройку совместимости. Добавление остановлено.')
    value = result.get('result', {}).get('value')
    if not isinstance(value, dict):
        raise RuntimeError('Steam не вернул настройки совместимости. Добавление остановлено.')
    return value


def configure_platform(app_id, platform, client):
    app_id = int(app_id)
    if platform == 'both':
        return {'unchanged': True}
    read = f'''(async()=>{{
      const d=await Promise.race([appDetailsStore.RequestAppDetails({app_id}),
        new Promise((_,reject)=>setTimeout(()=>reject(new Error('timeout')),5000))]);
      return {{tool:d.strCompatToolName||'',priority:d.nCompatToolPriority||0}};
    }})()'''
    previous = _evaluate(client, read)
    tool = previous.get('tool', '')
    is_proton = 'proton' in tool.lower()
    if platform == 'linux':
        if is_proton:
            raise ValueError('Для игры выбран Proton, но источник предоставляет только файлы Linux. Отключите принудительную совместимость в свойствах игры Steam или выберите Windows-источник.')
        return previous
    if is_proton:
        return previous
    if tool and not tool.lower().startswith('steamlinuxruntime'):
        raise ValueError('Для игры выбран нестандартный инструмент совместимости. Выберите Proton в свойствах игры Steam и повторите добавление.')
    from ember.config import DATA
    folder = DATA / 'compatibility-backups'
    folder.mkdir(exist_ok=True)
    backup = folder / f'{app_id}-{time.time_ns()}.json'
    backup.write_text(json.dumps(previous), encoding='utf-8')
    backup.chmod(0o600)
    logger.info('Selecting Steam stable Proton for Windows-only content: %s; previous=%s', app_id, tool)
    try:
        client.evaluate(f'SteamClient.Apps.SpecifyCompatTool({app_id}, "proton-stable")')
        deadline = time.monotonic() + 4
        while True:
            current = _evaluate(client, read)
            if 'proton' in current.get('tool', '').lower():
                return current
            if time.monotonic() >= deadline:
                raise RuntimeError('Steam не подтвердил выбор Proton. Добавление остановлено.')
            time.sleep(.1)
    except Exception:
        restore = tool if previous.get('priority', 0) >= 250 else ''
        try:
            client.evaluate(f'SteamClient.Apps.SpecifyCompatTool({app_id}, {json.dumps(restore)})')
        except Exception:
            logger.warning('Could not restore compatibility selection for %s; backup=%s', app_id, backup, exc_info=True)
        raise


def ensure_registration_platform(parsed):
    from sff.network.steam_client import fetch_app_info_http
    info = fetch_app_info_http(parsed.app_id)
    if not isinstance(info, dict):
        raise ValueError('Не удалось получить данные платформы Steam. Добавление остановлено; повторите позже.')
    ids = {str(p.depot_id) for p in parsed.depots if p.decryption_key}
    platform = required_platform(info, ids)
    logger.debug('Registration content platform for %s: %s', parsed.app_id, platform)
    client = _steam_client()
    try:
        return configure_platform(parsed.app_id, platform, client)
    finally:
        client.close()


def prepare_registration_prefixes(steam, app_id):
    from sff.core.storage.vdf import get_steam_libs
    from ember.host import prepare_compatdata
    for library in get_steam_libs(Path(steam)):
        prepare_compatdata(steam, library, app_id)
