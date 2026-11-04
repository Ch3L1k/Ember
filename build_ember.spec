# Ember — Copyright (C) 2026 Ember contributors.
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_data_files, copy_metadata

root = Path(SPECPATH)
os.environ['PATH'] = os.pathsep.join((str(Path(sys.executable).parent), str(Path(sys.base_prefix)),
    str(Path(sys.base_prefix) / 'DLLs'), str(Path(os.environ['SystemRoot']) / 'System32'), os.environ['SystemRoot']))
datas = [(str(root / path), path) for path in (
    'ember/web', 'ember/millennium', 'sff/webui', 'sff/locales', 'sff/gui/resources',
    'lab/web', 'third_party_licenses')]
datas += [(str(root / name), '.') for name in ('LICENSE', 'EMBER-NOTICES.txt', 'THIRD-PARTY.txt')]
datas += collect_data_files('rich')
hidden = collect_submodules('steam') + collect_submodules('sff') + collect_submodules('ember')
hidden += ['lab.prepare', 'lab.check_window', 'PyQt6.QtTest', 'PyQt6.QtWebEngineWidgets', 'PyQt6.QtWebChannel',
           'keyring.backends.Windows', 'keyrings.alt.file', 'gevent.libuv.loop', 'gevent.libev.corecext']
for package in ('gevent', 'gevent-eventemitter', 'steam', 'keyring', 'keyrings.alt'):
    datas += copy_metadata(package)
a = Analysis([str(root / 'EmberRuntime.py')], pathex=[str(root)], datas=datas,
             hiddenimports=hidden, excludes=['tkinter', 'matplotlib', 'scipy', 'IPython',
             'PyQt5', 'PySide6', 'pytest', 'seleniumbase', 'zendriver'], noarchive=False)
for destination, source, kind in a.binaries:
    if '/.cache/codex-runtimes/' in source.replace('\\', '/').lower():
        raise RuntimeError('Unexpected dependency from the development tool PATH: ' + destination)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='Ember', console=False,
          icon=str(root / 'ember/web/Ember.ico'), upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name='Ember', upx=False)
