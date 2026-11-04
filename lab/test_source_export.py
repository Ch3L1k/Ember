# Ember — Copyright (C) 2026 Ember contributors.
# SPDX-License-Identifier: GPL-3.0-or-later
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile


class SourceExportTests(unittest.TestCase):
    def test_windows_checkout_exports_executable_linux_shell_scripts(self):
        path = Path(__file__).resolve().parents[1] / 'packaging/source.py'
        spec = importlib.util.spec_from_file_location('ember_source_export', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        required = ['EmberRuntime.py', 'ember/millennium/backend.lua',
                    'ember/millennium/frontend.js', 'ember/millennium/webkit.js',
                    'ember/web/Ember.ico', 'sff/webui/index.html', 'packaging/installer.nsi',
                    'build_ember.spec', 'requirements.txt', 'LICENSE', 'install.sh']
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'checkout'
            for name in required:
                file = root / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(b'fixture')
            (root / 'install.sh').write_bytes(b'#!/usr/bin/env bash\r\nset -euo pipefail\r\necho ready\r\n')
            with patch.object(module, 'ROOT', root):
                module.export(Path(temporary) / 'source')
            with zipfile.ZipFile(Path(temporary) / 'source.zip') as archive:
                self.assertEqual(archive.read('Ember/install.sh'),
                                 b'#!/usr/bin/env bash\nset -euo pipefail\necho ready\n')
