# Ember — Copyright (C) 2026 Ember contributors.
# SPDX-License-Identifier: GPL-3.0-or-later
import importlib.util
import os
from unittest.mock import patch
import subprocess
import tempfile
import unittest
from pathlib import Path

FILE = Path(__file__).resolve().parents[1] / 'packaging/terminal_installer.py'

class TerminalInstallerTests(unittest.TestCase):
    def setUp(self):
        clean = {k:v for k,v in os.environ.items() if k not in ("EMBER_DATA_DIR", "XDG_DATA_HOME", "XDG_CONFIG_HOME")}
        context = patch.dict(os.environ, clean, clear=True)
        context.start(); self.addCleanup(context.stop)

    def load(self):
        self.assertTrue(FILE.exists(), 'Terminal installer not implemented')
        spec = importlib.util.spec_from_file_location('ember_installer_test', FILE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def fixture(self, root):
        source = root / 'source'
        source.mkdir()
        for name in ['EmberRuntime.py', 'LICENSE', 'requirements-linux.txt']:
            (source / name).write_text('# fixture\n')
        (source / 'ember/web').mkdir(parents=True)
        (source / 'ember/web/Ember.png').write_bytes(b'fixture')
        (source / 'settings.bin').write_text('PRIVATE')
        return source

    def prepare(self, release):
        binary = release / '.venv/bin/python'
        binary.parent.mkdir(parents=True)
        binary.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
        binary.chmod(0o755)

    def test_install_excludes_state_and_launcher_handles_spaces(self):
        m = self.load()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); home = root / 'test home'; home.mkdir()
            prefix = home / 'app space'
            m.install(self.fixture(root), prefix, home, self.prepare)
            current = (prefix / 'current').resolve()
            self.assertFalse((current / 'settings.bin').exists())
            result = subprocess.run([str(home / '.local/bin/ember'), 'arg with spaces'], capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout.splitlines(), [str(current / 'EmberRuntime.py'), 'arg with spaces'])

    def test_failed_update_preserves_current_and_launchers(self):
        m = self.load()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); home = root / 'home'; home.mkdir(); source = self.fixture(root)
            prefix = home / 'app'
            m.install(source, prefix, home, self.prepare)
            old = (prefix / 'current').resolve(); launcher = home / '.local/bin/ember'; old_bytes = launcher.read_bytes()
            def fail(_): raise RuntimeError('pip failed')
            with self.assertRaisesRegex(RuntimeError, 'pip failed'):
                m.install(source, prefix, home, fail)
            self.assertEqual((prefix / 'current').resolve(), old)
            self.assertEqual(launcher.read_bytes(), old_bytes)
            self.assertEqual(len(list((prefix / 'versions').iterdir())), 1)

    def test_foreign_launcher_and_unmarked_target_are_preserved(self):
        m = self.load()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); home = root / 'home'; home.mkdir(); source = self.fixture(root)
            launcher = home / '.local/bin/ember'; launcher.parent.mkdir(parents=True); launcher.write_text('another app')
            with self.assertRaises(RuntimeError): m.install(source, home / 'app', home, self.prepare)
            self.assertEqual(launcher.read_text(), 'another app')
            launcher.unlink(); (home / 'app').mkdir(); (home / 'app/keep').write_text('mine')
            with self.assertRaises(RuntimeError): m.install(source, home / 'app', home, self.prepare)
            self.assertEqual((home / 'app/keep').read_text(), 'mine')

    def test_uninstall_preserves_user_data_and_foreign_replacement(self):
        m = self.load()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); home = root / 'home'; home.mkdir(); prefix = home / 'app'
            m.install(self.fixture(root), prefix, home, self.prepare)
            data = home / '.local/share/ember/Desktop'; data.mkdir(parents=True); (data / 'save').write_text('keep')
            launcher = home / '.local/bin/ember'; launcher.write_text('replacement')
            m.uninstall(prefix, home)
            self.assertEqual((data / 'save').read_text(), 'keep')
            self.assertEqual(launcher.read_text(), 'replacement')
            self.assertFalse(prefix.exists())

    def test_target_cannot_be_home_or_source(self):
        m = self.load()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); home = root / 'home'; home.mkdir(); source = self.fixture(root)
            for prefix in (home, source, source / 'inside'):
                with self.assertRaises((ValueError, RuntimeError)): m.install(source, prefix, home, self.prepare)

if __name__ == '__main__': unittest.main()
