# Ember — Copyright (C) 2026 Ember contributors.
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details (LICENSE).

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ember.desktop import live_runtime, supervise_backend
from ember.launch import install_root, launch_command
from ember.millennium_bootstrap import main as bootstrap
from ember.server import LocalServer


class RecoveryTests(unittest.TestCase):
    def test_source_entry_starts_from_an_unrelated_working_directory(self):
        with tempfile.TemporaryDirectory(prefix='ember launch ') as folder:
            environment = dict(os.environ)
            environment.pop('PYTHONPATH', None)
            command = launch_command('--can-update')
            self.assertEqual(Path(command[1]), install_root() / 'EmberRuntime.py')
            result = subprocess.run(command, cwd=folder, env=environment, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0, timeout=15)
            self.assertIn(result.returncode, (0, 2))

    def test_runtime_requires_a_current_authenticated_backend(self):
        server = LocalServer(Mock(methods={}, signals={}), Mock(cursor=0), 'current-token')
        server.start()
        try:
            with tempfile.TemporaryDirectory() as folder:
                runtime = Path(folder) / 'runtime.json'
                data = {'mode': 'desktop', 'origin': server.origin, 'token': 'expired-token'}
                runtime.write_text(json.dumps(data))
                self.assertIsNone(live_runtime(Path(folder)))
                data['token'] = 'current-token'
                runtime.write_text(json.dumps(data))
                self.assertEqual(live_runtime(Path(folder)), data)
                data['origin'] = 'https://untrusted.example'
                runtime.write_text(json.dumps(data))
                with patch('ember.desktop.read_json', side_effect=AssertionError('Must stay local')):
                    self.assertIsNone(live_runtime(Path(folder)))
        finally:
            server.shutdown()
            server.server_close()

    @unittest.skipUnless(os.name == 'nt', 'Windows launcher')
    def test_bootstrap_waits_for_readiness_before_returning(self):
        ready = {'integration': 'millennium'}
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, LOCALAPPDATA=folder):
            with patch('ember.desktop.live_runtime', side_effect=[None, None, ready]) as read:
                with patch('ember.millennium_bootstrap.subprocess.Popen') as start, patch('ember.millennium_bootstrap.time.sleep'), patch('ember.millennium_bootstrap.logging.basicConfig'):
                    start.return_value.poll.return_value = None
                    bootstrap()
                    self.assertEqual(read.call_count, 3)
                    self.assertEqual(start.call_count, 1)
                    self.assertIn('EmberRuntime.py', str(start.call_args.args[0]))
                    self.assertEqual(start.call_args.kwargs['creationflags'], subprocess.CREATE_NO_WINDOW)

    @unittest.skipUnless(os.name == 'nt', 'Windows launcher')
    def test_bootstrap_reports_failure_and_does_not_wait_forever(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, LOCALAPPDATA=folder):
            with patch('ember.desktop.live_runtime', return_value=None), patch('ember.millennium_bootstrap.logging.basicConfig'):
                with patch('ember.millennium_bootstrap.subprocess.Popen') as start:
                    start.return_value.poll.return_value = 1
                    with self.assertRaisesRegex(RuntimeError, 'could not start'):
                        bootstrap()
                    start.return_value.poll.return_value = None
                    with patch('ember.millennium_bootstrap.time.monotonic', side_effect=[0, 21]):
                        with self.assertRaises(TimeoutError):
                            bootstrap()

    @unittest.skipUnless(os.name == 'nt', 'Windows launcher')
    def test_supervisor_recovers_a_crash_but_respects_normal_shutdown(self):
        failed, stopped = Mock(returncode=1), Mock(returncode=0)
        failed.poll.return_value, stopped.poll.return_value = 1, 0
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch('ember.desktop.subprocess.Popen', side_effect=[failed, stopped]) as start:
                with patch('ember.desktop.steam_processes', return_value=[object()]), patch('ember.desktop.time.sleep'):
                    self.assertEqual(supervise_backend(['fixture'], root, {}, root, root / 'steam.exe'), 0)
                    self.assertEqual(start.call_count, 2)
            with patch('ember.desktop.subprocess.Popen', return_value=stopped) as start:
                self.assertEqual(supervise_backend(['fixture'], root, {}, root, root / 'steam.exe'), 0)
                self.assertEqual(start.call_count, 1)

    @unittest.skipUnless(os.name == 'nt', 'Windows launcher')
    def test_supervisor_bounds_crash_retries_and_stops_when_steam_exits(self):
        failed = Mock(returncode=1)
        failed.poll.return_value = 1
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch('ember.desktop.subprocess.Popen', return_value=failed) as start:
                with patch('ember.desktop.steam_processes', return_value=[object()]), patch('ember.desktop.time.sleep'):
                    self.assertEqual(supervise_backend(['fixture'], root, {}, root, root / 'steam.exe'), 1)
                    self.assertEqual(start.call_count, 4)
            with patch('ember.desktop.subprocess.Popen', return_value=failed) as start:
                with patch('ember.desktop.steam_processes', return_value=[]):
                    self.assertEqual(supervise_backend(['fixture'], root, {}, root, root / 'steam.exe'), 1)
                    self.assertEqual(start.call_count, 1)


if __name__ == '__main__':
    unittest.main()
