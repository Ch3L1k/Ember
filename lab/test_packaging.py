# Ember — Copyright (C) 2026 Ember contributors.
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ember.launch import install_root, launch_command
from ember.millennium import PLUGIN_ID, prepare_adapter, remove_owned_adapter
from ember.desktop import check_runtime_owner


class PackagingTests(unittest.TestCase):
    def test_new_installation_does_not_reuse_an_old_source_backend(self):
        with patch('ember.desktop.psutil.Process') as process:
            process.side_effect = [SimpleNamespace(exe=lambda: str(Path(sys.executable).with_name('another-python.exe'))), SimpleNamespace(exe=lambda: sys.executable)]
            with self.assertRaisesRegex(RuntimeError, 'другая установка'):
                check_runtime_owner({'pid': 123})
            process.side_effect = [SimpleNamespace(exe=lambda: sys.executable), SimpleNamespace(exe=lambda: sys.executable)]
            check_runtime_owner({'pid': 123})

    def test_frozen_launch_reuses_executable_and_preserves_arguments(self):
        with patch.object(sys, 'frozen', True, create=True), patch.object(sys, 'executable', r'C:\Apps\Ember Preview\Ember.exe'):
            self.assertEqual(launch_command('--backend'), [sys.executable, '--backend'])
            self.assertEqual(install_root(), Path(sys.executable).resolve().parent)

    def test_source_launch_uses_current_python_module(self):
        with patch.object(sys, 'frozen', False, create=True):
            expected = Path(sys.executable).with_name('pythonw.exe') if os.name == 'nt' else Path(sys.executable)
            self.assertEqual(launch_command('--backend'), [str(expected), str(install_root() / 'EmberRuntime.py'), '--backend'])

    @unittest.skipUnless(os.name == 'nt', 'Windows windowed runtime')
    def test_console_and_windowed_python_from_same_installation_share_backend(self):
        with patch('ember.desktop.psutil.Process') as process:
            process.side_effect = [SimpleNamespace(exe=lambda: sys.executable), SimpleNamespace(exe=lambda: str(Path(sys.executable).with_name('pythonw.exe')))]
            check_runtime_owner({'pid': 123})

    @unittest.skipUnless(os.name == 'nt', 'Windows windowed runtime')
    def test_source_adapter_launches_windowed_python(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(sys, 'frozen', False, create=True):
            with patch.dict(os.environ, LOCALAPPDATA=directory):
                target = prepare_adapter(Path(directory) / 'Steam')
                command = (target / 'backend/main.lua').read_text(encoding='utf-8')
                self.assertIn('pythonw.exe', command)
                self.assertIn('EmberRuntime.py --millennium-bootstrap', command)

    def test_frozen_adapter_does_not_reference_development_python(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / 'Ember Preview/Ember.exe'
            with patch.object(sys, 'frozen', True, create=True), patch.object(sys, 'executable', str(executable)), patch.dict(os.environ, LOCALAPPDATA=str(root / 'Data')):
                target = prepare_adapter(root / 'Steam')
                metadata = json.loads((target / 'plugin.json').read_text())
                template = (target / 'backend/main.lua').read_text(encoding='utf-8')
                self.assertEqual(metadata['ember_install_dir'], str(executable.parent.resolve()))
                self.assertIn('--millennium-bootstrap', template)
                self.assertIn('Ember.exe', template)
                self.assertNotIn('.venv', template)

    def test_uninstaller_only_removes_owned_adapter_with_steam_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'Steam/millennium/plugins' / PLUGIN_ID
            target.mkdir(parents=True)
            (target / 'plugin.json').write_text(json.dumps({'ember_install_dir': str(install_root())}))
            keep = root / 'Steam/steamapps/keep.txt'
            keep.parent.mkdir()
            keep.write_text('game data')
            with patch('ember.config.steam_path', return_value=root / 'Steam'), patch('ember.desktop.steam_processes', return_value=[object()]):
                with self.assertRaisesRegex(RuntimeError, 'Close Steam'):
                    remove_owned_adapter()
                self.assertTrue(target.exists())
            with patch('ember.config.steam_path', return_value=root / 'Steam'), patch('ember.desktop.steam_processes', return_value=[]):
                remove_owned_adapter()
            self.assertFalse(target.exists())
            self.assertEqual(keep.read_text(), 'game data')

    def test_uninstaller_keeps_adapter_from_another_installation(self):
        with tempfile.TemporaryDirectory() as directory:
            steam = Path(directory)
            target = steam / 'millennium/plugins' / PLUGIN_ID
            target.mkdir(parents=True)
            metadata = target / 'plugin.json'
            metadata.write_text(json.dumps({'ember_install_dir': 'another installation'}))
            with patch('ember.config.steam_path', return_value=steam):
                remove_owned_adapter()
            self.assertTrue(metadata.exists())


if __name__ == '__main__':
    unittest.main()
