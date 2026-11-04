# Ember — Copyright (C) 2026 Ember contributors.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Per-user terminal installer. Build a release before publishing its launchers."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parent.parent
MARKER = '.ember-install.json'
TREES = ('ember', 'sff', 'packaging', 'third_party_licenses', 'docs')
FILES = ('EmberRuntime.py', 'Ember.py', 'LICENSE', 'EMBER-NOTICES.txt', 'THIRD-PARTY.txt',
         'requirements-linux.txt', 'README.md', 'README-linux.md', 'install.sh')
DENY = {'__pycache__', 'fallback_depotkeys.json', 'fallback_tokens.json', 'trionine_depotkeys.json',
        'contributor_state.json', 'settings.bin', 'api_cache.json', '.git'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def destinations(home):
    return (home / '.local/bin/ember', home / '.local/share/applications/ember.desktop',
            home / '.local/share/icons/hicolor/256x256/apps/ember.png')


def validate(prefix, home, source=None):
    prefix = Path(prefix).absolute()
    if prefix.is_symlink() or prefix.resolve() != prefix:
        raise ValueError('Install path must not contain symbolic links.')
    if prefix == home or home.is_relative_to(prefix) or prefix == Path('/'):
        raise ValueError('Choose a separate application directory, not your home or filesystem root.')
    if source and (prefix.is_relative_to(source.resolve()) or source.resolve().is_relative_to(prefix)):
        raise ValueError('The install directory must be separate from the source directory.')
    if any(c in str(prefix) for c in ('\n', '\r', '\t', '%')):
        raise ValueError('Install path contains unsupported control characters or %.')
    if prefix.exists():
        marker = prefix / MARKER
        if not marker.is_file() or marker.is_symlink():
            raise RuntimeError('This directory is not managed by Ember. Choose an empty new path.')
        data = json.loads(marker.read_text())
        if data.get('format') != 1 or data.get('prefix') != str(prefix) or data.get('home') != str(home):
            raise RuntimeError('Installation metadata does not match this location.')
        for child in prefix.iterdir():
            if child.name not in {MARKER, 'versions', 'current'}:
                raise RuntimeError('Unexpected file in installation directory: ' + child.name)
        versions = prefix / 'versions'
        if versions.is_symlink():
            raise RuntimeError('The versions directory must not be a symbolic link.')
        current = prefix / 'current'
        if not current.is_symlink() or not current.resolve().is_relative_to(versions):
            raise RuntimeError('Invalid current-version link.')
        return data
    return None


def running(prefix):
    for item in Path('/proc').glob('[0-9]*/cmdline'):
        try:
            args = item.read_bytes().split(b'\0')
            if any(b'EmberRuntime.py' in a and str(prefix).encode() in a for a in args):
                return True
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
    return False


def copy_source(source, target):
    for name in FILES:
        path = source / name
        if path.is_file() and not path.is_symlink():
            shutil.copy2(path, target / name)
    for name in TREES:
        origin = source / name
        if not origin.is_dir() or origin.is_symlink():
            continue
        for folder, dirs, files in os.walk(origin, followlinks=False):
            dirs[:] = [d for d in dirs if d not in DENY and not (Path(folder) / d).is_symlink()]
            for filename in files:
                path = Path(folder) / filename
                if filename in DENY or path.is_symlink() or path.suffix in {'.pyc', '.pyo'}:
                    continue
                destination = target / path.relative_to(source)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)
    for name in ('EmberRuntime.py', 'LICENSE', 'requirements-linux.txt', 'ember/web/Ember.png'):
        if not (target / name).is_file():
            raise RuntimeError('Incomplete source archive: ' + name)


def prepare_environment(release):
    commands = [
        [sys.executable, '-m', 'venv', str(release / '.venv')],
        [str(release / '.venv/bin/python'), '-m', 'pip', 'install', '-r', str(release / 'requirements-linux.txt')],
        [str(release / '.venv/bin/python'), '-m', 'pip', 'install', 'steam==1.4.4', '--no-deps'],
        [str(release / '.venv/bin/python'), '-c', 'import ssl, psutil, yaml, steam; from PyQt6 import QtWidgets, QtWebEngineWidgets; import ember.entry'],
    ]
    for index, command in enumerate(commands, 1):
        print(f'  [{index}/4] ' + ('Create Python environment', 'Install dependencies', 'Install Steam library', 'Check runtime')[index - 1], flush=True)
        subprocess.run(command, cwd=release, check=True)


def atomic_write(path, content, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.ember-' + uuid.uuid4().hex)
    try:
        temporary.write_bytes(content)
        temporary.chmod(mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def integration_files(home, prefix):
    data = Path(os.environ.get('EMBER_DATA_DIR') or (Path(os.environ.get('XDG_DATA_HOME', home / '.local/share')) / 'ember/Desktop'))
    metadata = data / 'autostart.json'
    if not metadata.exists():
        return None
    payload = json.loads(metadata.read_text(encoding='utf-8'))
    current = (prefix / 'current').resolve()
    expected = [str(current / '.venv/bin/python'), str(current / 'EmberRuntime.py'), '--watch-steam']
    entry = Path(os.environ.get('XDG_CONFIG_HOME', home / '.config')) / 'autostart/ember.desktop'
    if payload.get('command') != expected or payload.get('entry') != str(entry):
        raise RuntimeError('Steam integration belongs to another Ember installation.')
    if metadata.is_symlink() or entry.is_symlink() or not entry.is_file() or 'X-Ember-Owned=true' not in entry.read_text():
        raise RuntimeError('Steam integration ownership could not be verified.')
    return metadata, entry, payload


def desktop_quote(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$') + '"'


def install(source, prefix, home, prepare=prepare_environment):
    source, prefix, home = Path(source).resolve(), Path(prefix).absolute(), Path(home).resolve()
    previous = validate(prefix, home, source)
    if running(prefix):
        raise RuntimeError('Close Ember first: ember --stop. Steam does not need to close.')
    targets = destinations(home)
    for target in targets:
        if target.is_symlink() or (target.exists() and (not previous or previous['files'].get(str(target)) != digest(target))):
            raise RuntimeError('An existing or modified launcher would be overwritten: ' + str(target))
    integration = integration_files(home, prefix) if previous else None
    release = prefix / 'versions' / (time.strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8])
    release.mkdir(parents=True)
    old_link = os.readlink(prefix / 'current') if previous else None
    old_files = {p: (p.read_bytes(), p.stat().st_mode & 0o777) if p.exists() else None for p in targets}
    old_marker = (prefix / MARKER).read_bytes() if previous else None
    integration_before = {p: p.read_bytes() for p in integration[:2]} if integration else {}
    switched = False
    try:
        print('  Copying application files…', flush=True)
        copy_source(source, release)
        prepare(release)
        launcher = '#!/bin/sh\nexec ' + shlex.quote(str(release / '.venv/bin/python')) + ' ' + shlex.quote(str(release / 'EmberRuntime.py')) + ' "$@"\n'
        escaped = str(targets[0]).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$')
        desktop = '[Desktop Entry]\nType=Application\nName=Ember\nComment=Steam library and game tools\nExec="' + escaped + '"\nIcon=ember\nTerminal=false\nCategories=Game;Utility;\nStartupWMClass=Ember\n'
        switched = True
        atomic_write(targets[0], launcher.encode(), 0o755)
        atomic_write(targets[1], desktop.encode())
        atomic_write(targets[2], (release / 'ember/web/Ember.png').read_bytes())
        if integration:
            metadata, entry, payload = integration
            command = [str(release / '.venv/bin/python'), str(release / 'EmberRuntime.py'), '--watch-steam']
            payload['command'] = command
            lines = [line for line in entry.read_text(encoding='utf-8').splitlines() if not line.startswith('Exec=')]
            lines.append('Exec=' + ' '.join(map(desktop_quote, command)))
            atomic_write(entry, ('\n'.join(lines) + '\n').encode())
            atomic_write(metadata, json.dumps(payload).encode(), 0o600)
        temp_link = prefix / ('.current-' + uuid.uuid4().hex)
        temp_link.symlink_to(release.relative_to(prefix))
        os.replace(temp_link, prefix / 'current')
        metadata = {'format': 1, 'prefix': str(prefix), 'home': str(home),
                    'files': {str(p): digest(p) for p in targets}}
        atomic_write(prefix / MARKER, (json.dumps(metadata, indent=2) + '\n').encode(), 0o600)
    except BaseException:
        if switched:
            for path, content in integration_before.items():
                atomic_write(path, content)
            for path, old in old_files.items():
                if old is None: path.unlink(missing_ok=True)
                else: atomic_write(path, old[0], old[1])
            (prefix / 'current').unlink(missing_ok=True)
            if old_link is not None: (prefix / 'current').symlink_to(old_link)
            if old_marker is not None: atomic_write(prefix / MARKER, old_marker, 0o600)
        shutil.rmtree(release)
        if not previous:
            (prefix / 'versions').rmdir()
            prefix.rmdir()
        raise
    return release


def uninstall(prefix, home):
    prefix, home = Path(prefix).absolute(), Path(home).resolve()
    previous = validate(prefix, home)
    if not previous:
        raise RuntimeError('No managed installation found at this path.')
    if running(prefix):
        raise RuntimeError('Close Ember first: ember --stop.')
    if integration_files(home, prefix):
        current = (prefix / 'current').resolve()
        subprocess.run([str(current / '.venv/bin/python'), str(current / 'EmberRuntime.py'), '--uninstall-integration'], check=True)
    for path in destinations(home):
        if path.is_file() and not path.is_symlink() and previous['files'].get(str(path)) == digest(path):
            path.unlink()
    shutil.rmtree(prefix)


def main():
    parser = argparse.ArgumentParser(description='Ember terminal installer for Linux')
    parser.add_argument('--action', choices=('install', 'update', 'uninstall', 'check'))
    parser.add_argument('--prefix', type=Path, default=Path.home() / '.local/opt/ember')
    parser.add_argument('--yes', action='store_true', help='Confirm the selected action without prompting')
    args = parser.parse_args()
    print('\n  EMBER\n  Windows & Linux · Linux installer\n')
    if sys.platform != 'linux' or platform.machine().lower() not in ('x86_64', 'amd64'):
        raise RuntimeError('This installer requires Linux x86_64. On Windows use Ember-Setup.exe.')
    if sys.version_info < (3, 11):
        raise RuntimeError('Python 3.11 or newer is required.')
    if os.geteuid() == 0:
        raise RuntimeError('Run as your normal user, without sudo.')
    action = args.action
    if action is None:
        if not sys.stdin.isatty(): parser.error('Use --action install --yes in noninteractive mode.')
        print('  1  Install / update\n  2  Check requirements\n  3  Uninstall\n  0  Exit\n')
        choice = input('  Choose [1]: ').strip() or '1'
        if choice == '0': return 0
        action = {'1': 'install', '2': 'check', '3': 'uninstall'}.get(choice)
        if action is None: raise ValueError('Unknown menu item.')
        chosen = input(f'  Install folder [{args.prefix}]: ').strip()
        if chosen: args.prefix = Path(chosen).expanduser()
    import venv
    import ensurepip
    print(f'  Python: {platform.python_version()}\n  Folder: {args.prefix}\n  Account: {Path.home().name}\n')
    if action == 'check':
        for name, path in [('Steam', Path.home() / '.local/share/Steam'), ('Steam (alternate)', Path.home() / '.steam/steam'),
                           ('SLSsteam', Path.home() / '.local/share/SLSsteam/SLSsteam.so'),
                           ('lumalinux', Path.home() / '.local/share/lumalinux/liblumalinux.so')]:
            print(f'  {name}: {"found" if path.exists() else "not found at standard path"}')
        print('\n  Python environment tools available. Game registration requires separately installed Linux modules.')
        return 0
    if not args.yes and input(f'  {action.capitalize()} Ember? [y/N]: ').strip().lower() not in ('y', 'yes', 'д', 'да'):
        print('  Cancelled.'); return 0
    import fcntl
    lock_dir = Path.home() / '.local/state/ember-installer'
    lock_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (lock_dir / 'lock').open('w') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise RuntimeError('Another Ember installer is already running.')
        if action == 'uninstall':
            uninstall(args.prefix, Path.home())
            print('\n  Removed. Settings, games and saves have been kept.')
        else:
            install(ROOT, args.prefix, Path.home())
            print('\n  Installed. Open Ember from the application menu, or run ~/.local/bin/ember.\n  On first launch Ember configures its Steam UI integration. Restart Steam normally if requested.\n  Game-registration modules are separate prerequisites; this installer does not install them.')
    return 0


if __name__ == '__main__':
    try: raise SystemExit(main())
    except KeyboardInterrupt:
        print('\n  Cancelled.', file=sys.stderr); raise SystemExit(130)
    except Exception as error:
        print('\n  Installation stopped: ' + str(error), file=sys.stderr); raise SystemExit(1)
