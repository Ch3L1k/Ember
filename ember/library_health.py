# Ember — Copyright (C) 2026 Ember contributors.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Inspect library statistics and repair known Ember integration settings."""
import json
import logging
import os
from pathlib import Path
import re
import shutil
import tempfile
import threading
import time

import psutil

from ember.library import Library

logger = logging.getLogger(__name__)
_LOCK = threading.Lock()
_FLAG = 'LUMA_NO_SLS_ACH_UNBLOCK'


def launcher_update(text):
    block = re.search(r'(?m)^# Ember native Steam installer \(lumalinux\)\r?\nif [^\n]+; then\r?\n(?P<body>(?:(?!^fi\b).|\n)*?)^fi\b', text)
    if not block or text.count(_FLAG) != 1:
        return None
    flag = re.search(r'(?m)^    export LUMA_NO_SLS_ACH_UNBLOCK=1\r?\n', block['body'])
    if not flag:
        return None
    start = block.start('body') + flag.start()
    return text[:start] + text[start + len(flag[0]):]


def _launcher_text(path):
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_uid != os.getuid():
            return None
        return path.read_bytes().decode('utf-8')
    except (OSError, UnicodeError):
        logger.debug('Steam launcher could not be inspected', exc_info=True)
        return None


def repair_launcher(path, backups):
    path, backups = Path(path), Path(backups)
    with _LOCK:
        original = _launcher_text(path)
        updated = launcher_update(original) if original is not None else None
        if updated is None:
            return None
        backups.mkdir(parents=True, exist_ok=True)
        backup = backups / ('steam-' + str(time.time_ns()) + '.bak')
        shutil.copy2(path, backup)
        fd, name = tempfile.mkstemp(prefix='.ember-steam-', dir=path.parent)
        pending = Path(name)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8', newline='') as handle:
                handle.write(updated)
            shutil.copymode(path, pending)
            if _launcher_text(path) != original:
                raise RuntimeError('Настройки запуска изменились. Повторите проверку.')
            pending.replace(path)
        finally:
            pending.unlink(missing_ok=True)
        logger.info('Enabled achievement compatibility for the next Steam start; backup: %s', backup)
        return str(backup)


def achievement_hook():
    candidates = [Path(os.environ.get('XDG_RUNTIME_DIR', '/run/user/' + str(os.getuid()))) / 'lumalinux/status.json',
                  Path.home() / '.cache/lumalinux/status.json']
    for path in candidates:
        try:
            status = json.loads(path.read_text())
            process = psutil.Process(int(status['pid']))
            if process.name() != 'steam' or path.stat().st_mtime + 2 < process.create_time():
                continue
            if status.get('blocked'):
                return 'unavailable'
            return status.get('hooks', {}).get('SlsAchievementUnblock', 'unavailable')
        except (OSError, ValueError, KeyError, psutil.Error):
            logger.debug('Achievement hook status unavailable from %s', path, exc_info=True)
    return 'unavailable'


def steam_snapshot(app_id, refresh=False):
    from ember.platform_selection import _steam_client
    client = _steam_client()
    try:
        expression = '''(async () => {
            const id = APP_ID;
            let subscription;
            try {
                subscription = appDetailsStore.RegisterForAppData(id, () => {});
                const detail = await Promise.race([
                    appDetailsStore.RequestAppDetails(id),
                    new Promise((_, reject) => setTimeout(() => reject(Error('Steam details timeout')), 4000))
                ]);
                if (REFRESH) await Promise.race([
                    appDetailsStore.RequestAchievements(id),
                    new Promise((_, reject) => setTimeout(() => reject(Error('Steam achievements timeout')), 4000))
                ]);
                const play = await Promise.race([
                    SteamClient.Apps.GetPlaytime(id),
                    new Promise((_, reject) => setTimeout(() => reject(Error('Steam playtime timeout')), 4000))
                ]);
                if (REFRESH) {
                    const until = Date.now() + 2000;
                    while (!appDetailsStore.GetAchievements(id)?.nTotal && Date.now() < until)
                        await new Promise(resolve => setTimeout(resolve, 100));
                }
                const cached = appDetailsStore.GetAchievements(id);
                const achievements = cached?.nTotal ? cached : appDetailsStore.GetAppDetails(id)?.achievements;
                const overview = appStore.GetAppOverviewByAppID(id);
                return {minutes: play.nPlaytimeForever, last_played: play.rtLastTimePlayed,
                    local_last_played: overview?.rt_last_time_locally_played || 0,
                    total: achievements?.nTotal || 0, achieved: achievements?.nAchieved || 0};
            } finally { subscription?.unregister(); }
        })()'''.replace('APP_ID', str(int(app_id))).replace('REFRESH', 'true' if refresh else 'false')
        response = client.call('Runtime.evaluate', {'expression': expression, 'returnByValue': True, 'awaitPromise': True}, timeout=16)
        if response.get('exceptionDetails'):
            raise RuntimeError('Steam не вернул статистику. Повторите проверку после загрузки библиотеки.')
        value = response.get('result', {}).get('value')
        if not isinstance(value, dict) or not isinstance(value.get('minutes'), (int, float)):
            raise RuntimeError('Steam не вернул статистику. Повторите проверку после загрузки библиотеки.')
        return value
    finally:
        client.close()


def run(bridge, app_id, repair=False):
    from ember.config import DATA
    app_id = Library.app_id(str(app_id))
    if os.name == 'nt':
        return {'repairable': False, 'checks': [], 'message': 'Эта проверка предназначена для Linux-интеграции Steam.'}
    logger.info('Library statistics %s started for app %s', 'repair' if repair else 'check', app_id)
    managed = app_id in Library(bridge._steam_path, DATA).registrations()
    launcher = Path.home() / '.local/bin/steam'
    original = _launcher_text(launcher)
    can_enable = managed and original is not None and launcher_update(original) is not None
    backup = repair_launcher(launcher, DATA / 'library-statistics-backups') if repair and can_enable else None
    hook = achievement_hook() if managed else None
    checks = []
    if managed:
        checks.append('Модуль достижений подключён.' if hook == 'installed' else 'Модуль достижений не подключён в текущем процессе Steam.')
    if can_enable:
        checks.append('В запуске Ember отключён модуль достижений.' if not backup else 'Модуль достижений включён для следующего запуска Steam.')
    restart = bool(backup) or (managed and hook == 'disabled' and not can_enable)
    if restart:
        checks.append('Полностью перезапустите Steam, затем повторите проверку. Игры автоматически не закрываются.')
    stats = None
    try:
        stats = steam_snapshot(app_id, refresh=repair)
        checks.append('Статистика получена из Steam.')
        if stats['minutes'] == 0 and stats['local_last_played']:
            checks.append('Steam хранит ноль полных минут. Ember показывает короткий сеанс без изменения счётчика.')
        if stats['total'] == 0:
            checks.append('Steam пока не вернул список достижений, либо в игре их нет. Полученные достижения не подставляются вручную.')
    except Exception:
        logger.warning('Could not read library statistics for %s', app_id, exc_info=True)
        checks.append('Не удалось прочитать статистику. Откройте библиотеку Steam и повторите проверку.')
    if managed and hook != 'installed' and not can_enable and not restart:
        checks.append('Автоматическое включение недоступно: проверьте совместимость установленных модулей. Неизвестные настройки не изменены.')
    message = 'Проверка завершена.'
    if repair:
        if backup:
            message = 'Настройки сохранены. Требуется перезапуск Steam.'
        elif restart:
            message = 'Модуль отключён в запущенном Steam. Перезапустите Steam и повторите проверку.'
        elif stats is not None:
            message = 'Запрос обновления отправлен Steam. Проверьте карточку игры; при необходимости повторите проверку через несколько секунд.'
        else:
            message = 'Обновление статистики не подтверждено. Исправление не завершено.'
    return {'repairable': bool(can_enable or stats), 'checks': checks, 'statistics': stats,
            'restart_required': restart, 'backup': backup,
            'message': message}
