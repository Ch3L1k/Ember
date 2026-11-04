# Ember — Copyright (C) 2026 Ember contributors.
# GNU GPL version 3 or later; distributed without any warranty.
# See LICENSE for the full license and warranty disclaimer.

import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ember.appinfo_repair import patch_product_token, restore_product_token


def fixture():
    entries = b''
    for app_id in (12, 34):
        data = b'\x08'
        entries += struct.pack('<IIIIQ', app_id, 60 + len(data), 1, 123, 0) + b'h' * 20 + struct.pack('<I', 10) + b'd' * 20 + data
    entries += b'\0' * 4
    return b')DV\x07' + struct.pack('<IQ', 1, 16 + len(entries)) + entries + struct.pack('<I', 0)


class AppinfoRepairTests(unittest.TestCase):
    def test_patch_only_changes_the_selected_token_and_keeps_other_entries(self):
        original = fixture()
        repaired = patch_product_token(original, 34, 2**64 - 1)
        self.assertEqual(len(original), len(repaired))
        changed = [index for index, values in enumerate(zip(original, repaired)) if values[0] != values[1]]
        self.assertEqual(changed, list(range(101, 109)))
        self.assertEqual(patch_product_token(repaired, 34, 2**64 - 1), repaired)
        with self.assertRaises(ValueError):
            patch_product_token(original, 99, 123)
        for damaged in (original[:10], original[:-10], b'invalid'):
            with self.assertRaises(ValueError):
                patch_product_token(damaged, 34, 123)

    def test_live_steam_is_rejected_and_offline_write_has_a_verified_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / 'Steam/appcache/appinfo.vdf'
            target.parent.mkdir(parents=True)
            original = fixture()
            target.write_bytes(original)
            with patch('ember.desktop.steam_processes', return_value=[object()]):
                with self.assertRaises(RuntimeError):
                    restore_product_token(root / 'Steam', 34, 123, root / 'Backups')
                self.assertEqual(target.read_bytes(), original)
            with patch('ember.desktop.steam_processes', return_value=[]):
                result = restore_product_token(root / 'Steam', 34, 123, root / 'Backups')
            self.assertEqual(Path(result['backup']).read_bytes(), original)
            self.assertEqual(target.read_bytes(), patch_product_token(original, 34, 123))

    def test_live_steam_guard_uses_the_current_platform_executable(self):
        from ember.host import steam_executable
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / 'Steam/appcache/appinfo.vdf'
            target.parent.mkdir(parents=True)
            target.write_bytes(fixture())
            with patch('ember.desktop.steam_processes', return_value=[object()]) as running:
                with self.assertRaises(RuntimeError):
                    restore_product_token(root / 'Steam', 34, 123, root / 'Backups')
                running.assert_called_once_with(steam_executable(root / 'Steam'))

    def test_steam_restart_during_repair_leaves_original_intact(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / 'Steam/appcache/appinfo.vdf'
            target.parent.mkdir(parents=True)
            target.write_bytes(fixture())
            with patch('ember.desktop.steam_processes', side_effect=[[], [object()]]):
                with self.assertRaisesRegex(RuntimeError, 'restarted'):
                    restore_product_token(root / 'Steam', 34, 123, root / 'Backups')
            self.assertEqual(target.read_bytes(), fixture())
            self.assertEqual(list(target.parent.glob('*.tmp')), [])


if __name__ == '__main__':
    unittest.main()
