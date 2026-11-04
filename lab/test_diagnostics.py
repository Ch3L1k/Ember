# Ember — Copyright (C) 2026 Ember contributors.
# SPDX-License-Identifier: GPL-3.0-or-later
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ember import diagnostics as d

class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name); self.steam=self.root/'Steam'; self.lib=self.root/'Shared'
        self.source=self.lib/'steamapps/compatdata/480'
        (self.source/'pfx/drive_c/users/steamuser').mkdir(parents=True)
        (self.source/'pfx/drive_c/users/steamuser/save.dat').write_bytes(b'my save')
        (self.source/'pfx/dosdevices').mkdir()
        self.target=self.steam/'steamapps/compatdata/480'
        self.fs=patch.object(d,'filesystem',side_effect=lambda p: 'ntfs3' if Path(p).is_relative_to(self.lib) else 'btrfs')
        self.fs.start(); self.addCleanup(self.fs.stop)
        self.running=patch.object(d,'game_running',return_value=False)
        self.running.start();self.addCleanup(self.running.stop)
    def test_detects_missing_drive_on_ntfs(self):
        report=d.inspect_prefix(self.steam,self.lib,'480')
        self.assertTrue(report['repairable']); self.assertEqual(report['code'],'prefix_ntfs')
    def test_migration_preserves_saves_and_original(self):
        result=d.repair_prefix(self.steam,self.lib,'480')
        self.assertEqual(self.source.resolve(),self.target)
        self.assertEqual((self.target/'pfx/drive_c/users/steamuser/save.dat').read_bytes(),b'my save')
        self.assertEqual((Path(result['backup'])/'pfx/drive_c/users/steamuser/save.dat').read_bytes(),b'my save')
        self.assertFalse(d.inspect_prefix(self.steam,self.lib,'480')['repairable'])
    def test_existing_target_is_not_overwritten(self):
        self.target.mkdir(parents=True)
        with self.assertRaises(ValueError):d.repair_prefix(self.steam,self.lib,'480')
        self.assertFalse(self.source.is_symlink())
    def test_running_game_blocks_repair(self):
        with patch.object(d,'game_running',return_value=True):
            with self.assertRaises(ValueError):d.repair_prefix(self.steam,self.lib,'480')
        self.assertFalse(self.target.exists())
    def test_link_failure_restores_original_location(self):
        with patch.object(Path,'symlink_to',side_effect=OSError('denied')):
            with self.assertRaises(OSError):d.repair_prefix(self.steam,self.lib,'480')
        self.assertFalse(self.source.is_symlink())
        self.assertTrue((self.source/'pfx/drive_c/users/steamuser/save.dat').exists())
        self.assertFalse(self.target.exists())
        self.assertTrue(d.inspect_prefix(self.steam,self.lib,'480')['repairable'])
    def test_invalid_appid_refused(self):
        with self.assertRaises(ValueError):d.inspect_prefix(self.steam,self.lib,'../480')
    def test_dangling_prefix_never_replaced(self):
        import shutil
        shutil.rmtree(self.source); self.source.symlink_to(self.root/'missing')
        self.assertFalse(d.inspect_prefix(self.steam,self.lib,'480')['repairable'])
