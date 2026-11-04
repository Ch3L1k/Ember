# Ember — Copyright (C) 2026 Ember contributors.
# This program is free software under the GNU General Public License,
# version 3 or later. Distributed WITHOUT ANY WARRANTY. See LICENSE.

import hashlib
import logging
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time

from ember.host import game_running
from ember.library import Library

logger = logging.getLogger(__name__)
_LOCK = threading.Lock()
_NTFS = {'ntfs', 'ntfs3', 'fuseblk', 'exfat', 'vfat'}


def filesystem(path):
    path = Path(path).resolve()
    while not path.exists() and path != path.parent:
        path = path.parent
    result = subprocess.run(['findmnt', '-n', '-o', 'FSTYPE', '-T', str(path)],
                            capture_output=True, text=True, timeout=3, check=True)
    return result.stdout.strip()


def inspect_prefix(steam, library, app_id):
    app_id = Library.app_id(str(app_id))
    source = Path(library) / 'steamapps/compatdata' / app_id
    target = Path(steam).resolve() / 'steamapps/compatdata' / app_id
    if source.is_symlink() and not source.exists():
        return {'code': 'broken_link', 'repairable': False, 'message': 'Ссылка на окружение Proton повреждена. Автоматическое восстановление отключено.'}
    if not source.exists():
        return {'code': 'not_created', 'repairable': False, 'message': 'Окружение Proton ещё не создано. Сначала попробуйте запустить игру из Steam.'}
    fs = filesystem(source)
    if fs in _NTFS:
        return {'code': 'prefix_ntfs', 'repairable': not source.is_symlink() and not target.exists() and not target.is_symlink() and filesystem(target.parent) not in _NTFS,
                'message': 'Окружение Proton находится на файловой системе Windows. Его можно перенести на Linux-раздел, сохранив все данные и резервную копию.',
                'drive_c': (source/'pfx/dosdevices/c:').exists(), 'filesystem': fs}
    return {'code': 'prefix_ok', 'repairable': False, 'message': 'Окружение Proton находится на Linux-разделе.', 'filesystem': fs,
            'drive_c': (source/'pfx/dosdevices/c:').exists()}


def _inventory(root):
    entries = {}
    for parent, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            path = Path(parent)/name
            key = str(path.relative_to(root))
            if path.is_symlink():
                entries[key] = ('link', os.readlink(path))
            elif path.is_file():
                with path.open('rb') as handle:
                    entries[key] = ('file', hashlib.file_digest(handle, 'sha256').hexdigest())
            elif path.is_dir():
                entries[key] = ('dir',)
            else:
                raise ValueError('В окружении Proton найден специальный файл. Закройте игру и повторите проверку.')
    return entries


def repair_prefix(steam, library, app_id):
    with _LOCK:
        if game_running():
            raise ValueError('Закройте запущенные игры перед исправлением окружения Proton.')
        state = inspect_prefix(steam, library, app_id)
        if not state['repairable']:
            raise ValueError('Автоматический перенос недоступен: окружение уже перенесено либо папка назначения занята.')
        source = Path(library)/'steamapps/compatdata'/str(app_id)
        target = Path(steam).resolve()/'steamapps/compatdata'/str(app_id)
        before = _inventory(source)
        size = sum(p.stat().st_size for p in source.rglob('*') if p.is_file() and not p.is_symlink())
        target.parent.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(target.parent).free < size + 256*1024*1024:
            raise ValueError('На Linux-разделе недостаточно места для копии окружения Proton.')
        temporary = Path(tempfile.mkdtemp(prefix=f'.ember-{app_id}-', dir=target.parent))
        backup = source.with_name(source.name + '.ember-backup-' + str(time.time_ns()))
        logger.info('Copying Proton prefix for %s to %s', app_id, target)
        try:
            shutil.copytree(source, temporary, symlinks=True, dirs_exist_ok=True)
            if _inventory(temporary) != before or _inventory(source) != before:
                raise OSError('Проверка копии не прошла либо данные изменились во время копирования.')
            if game_running():
                raise ValueError('Игра запущена во время копирования. Перенос отменён.')
            if target.exists() or target.is_symlink():
                raise ValueError('Папка назначения появилась во время переноса; данные не заменены.')
            temporary.rename(target)
            committed = target.stat()
            try:
                source.rename(backup)
                try:
                    source.symlink_to(target, target_is_directory=True)
                except Exception:
                    backup.rename(source)
                    raise
            except Exception:
                # Remove only our verified copy, after the original has been restored.
                if source.is_dir() and not source.is_symlink() and _inventory(source) == before:
                    current = target.stat()
                    if (current.st_dev, current.st_ino) == (committed.st_dev, committed.st_ino) and _inventory(target) == before:
                        shutil.rmtree(target)
                raise
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
        logger.info('Proton prefix migrated for %s; original retained at %s', app_id, backup)
        return {'backup': str(backup), 'prefix': str(target),
                'message': 'Окружение Proton перенесено с проверкой копии. Сохранения сохранены. Запустите игру через Steam; успешный запуск ещё нужно проверить.'}


def run(bridge, app_id, repair=False):
    app_id = Library.app_id(str(app_id))
    from sff.core.storage.vdf import get_steam_libs, vdf_load
    steam = Path(bridge._steam_path).resolve()
    for library in get_steam_libs(steam):
        library = Path(library)
        acf = library/'steamapps'/f'appmanifest_{app_id}.acf'
        if acf.is_file():
            state = vdf_load(acf).get('AppState', {})
            break
    else:
        raise ValueError('Steam не содержит запись об установленной игре. Сначала установите её в Steam.')
    common = (library/'steamapps/common').resolve()
    folder = (common/str(state.get('installdir', ''))).resolve()
    if folder == common or not folder.is_relative_to(common):
        raise ValueError('Некорректная папка установки в манифесте Steam.')
    checks = []
    if not folder.is_dir() or not any(folder.iterdir()):
        checks.append('Файлы игры отсутствуют. Установите игру или проверьте целостность файлов в Steam.')
    else:
        checks.append('Папка игры найдена. Наличие всех файлов проверяется средствами Steam.')
    if os.name != 'nt':
        mount = subprocess.run(['findmnt','-n','-o','OPTIONS','-T',str(folder if folder.exists() else library)], capture_output=True,text=True,timeout=3)
        if 'noexec' in mount.stdout.strip().split(','):
            checks.append('Раздел смонтирован с noexec: запуск исполняемых файлов запрещён настройками Linux.')
    prefix = inspect_prefix(steam, library, app_id) if os.name != 'nt' else {'repairable': False, 'message': 'Диагностика Proton применяется только в Linux.'}
    checks.append(prefix['message'])
    if prefix.get('code') == 'prefix_ntfs' and not prefix.get('drive_c'):
        checks.append('Не найден диск C: Wine. Это препятствует запуску Windows-игр.')
    result = {'checks': checks, 'repairable': prefix['repairable'], 'code': prefix.get('code'),
              'message': 'Проверены локальные файлы и окружение. Совместимость игры, драйверов и античита требует отдельной проверки.'}
    if repair:
        result.update(repair_prefix(steam, library, app_id))
        result['repairable'] = False
        result['checks'] = run(bridge, app_id)['checks']
    return result
