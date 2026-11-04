# Ember — Copyright (C) 2026 Ember contributors.
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from ember.config import _windows_steam_path, steam_path


@unittest.skipUnless(os.name == "nt", "Windows registry discovery")
class SteamDiscoveryTests(unittest.TestCase):
    def test_machine_installation_works_without_current_user_key(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "steam.exe").touch()
            with patch("winreg.OpenKey", side_effect=[FileNotFoundError(), MagicMock()]), \
                    patch("winreg.QueryValueEx", return_value=(folder, 1)):
                self.assertEqual(_windows_steam_path(), root.resolve())

    def test_stale_user_path_does_not_hide_machine_installation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "steam.exe").touch()
            for invalid in (str(root / "removed"), "", None):
                with self.subTest(value=invalid), patch("winreg.OpenKey", return_value=MagicMock()), \
                        patch("winreg.QueryValueEx", side_effect=[(invalid, 1), (folder, 1)]):
                    self.assertEqual(_windows_steam_path(), root.resolve())

    def test_native_machine_registry_is_checked_when_other_keys_are_unavailable(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "steam.exe").touch()
            with patch("winreg.OpenKey", side_effect=[PermissionError(), FileNotFoundError(), MagicMock()]), \
                    patch("winreg.QueryValueEx", return_value=(folder, 1)):
                self.assertEqual(_windows_steam_path(), root.resolve())

    def test_missing_installation_has_an_actionable_error(self):
        with patch("winreg.OpenKey", side_effect=FileNotFoundError()):
            with self.assertRaisesRegex(FileNotFoundError, "Steam"):
                _windows_steam_path()

    def test_lab_requires_an_explicit_directory(self):
        with patch.dict(os.environ, {"EMBER_MODE": "lab"}), \
                patch("ember.config._windows_steam_path", side_effect=AssertionError("Must not probe real Steam")):
            with patch.dict(os.environ):
                os.environ.pop("EMBER_STEAM_DIR", None)
                with self.assertRaisesRegex(RuntimeError, "Lab requires"):
                    steam_path()


if __name__ == "__main__":
    unittest.main()
