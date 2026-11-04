# Ember — Copyright (C) 2026 Ember contributors.
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from ember.host import desktop_data, linux_lock
from ember.library import Library
from ember import linux_tools


class LinuxPortTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / "config/SLSsteam/config.yaml"
        self.config.parent.mkdir(parents=True)
        self.config.write_text(yaml.safe_dump({"AdditionalApps": [100, 200], "AppIds": [300], "SafeMode": True, "Unrelated": "keep"}))
        self.env = patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.root / "config"), "EMBER_MODE": "desktop"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.data_patch = patch.object(linux_tools, "DATA", self.root / "data")
        self.data_patch.start()
        self.addCleanup(self.data_patch.stop)

    def test_xdg_data_and_explicit_override(self):
        with patch.dict(os.environ, {"XDG_DATA_HOME": str(self.root / "xdg")}, clear=True):
            self.assertEqual(desktop_data(), self.root / "xdg/ember/Desktop")
        with patch.dict(os.environ, {"EMBER_DATA_DIR": str(self.root / "custom")}):
            self.assertEqual(desktop_data(), self.root / "custom")

    def test_duplicate_lock_does_not_enter_then_releases(self):
        path = self.root / "launcher.lock"
        with linux_lock(path) as first:
            self.assertTrue(first)
            with linux_lock(path) as second:
                self.assertFalse(second)
        with linux_lock(path) as third:
            self.assertTrue(third)

    def test_yaml_edit_retains_safety_and_unrelated_fields_with_backup(self):
        before = self.config.read_bytes()
        linux_tools.update_list("AppIds", "400", True)
        value = yaml.safe_load(self.config.read_text())
        self.assertEqual(value["AppIds"], [300, 400])
        self.assertIs(value["SafeMode"], True)
        self.assertEqual(value["Unrelated"], "keep")
        backup = next((self.root / "data/sls-backups").glob("*.yaml"))
        self.assertEqual(backup.read_bytes(), before)
        linux_tools.update_list("AppIds", "400", False)
        self.assertEqual(yaml.safe_load(self.config.read_text())["AppIds"], [300])

    def test_library_remove_restore_updates_only_selected_subscription(self):
        library = Library(self.root / "Steam", self.root / "data")
        library.plugins.mkdir(parents=True)
        plugin = library.plugins / "100.lua"
        plugin.write_text("addappid(100)\n")
        game = self.root / "Steam/steamapps/common/example"
        game.mkdir(parents=True)
        (game / "save.dat").write_bytes(b"save")
        library.remove("100", "Example")
        self.assertEqual(yaml.safe_load(self.config.read_text())["AdditionalApps"], [200])
        self.assertFalse(plugin.exists())
        self.assertEqual((game / "save.dat").read_bytes(), b"save")
        library.restore("100")
        self.assertEqual(set(yaml.safe_load(self.config.read_text())["AdditionalApps"]), {100, 200})
        self.assertTrue(plugin.is_file())

    def test_upstream_registration_is_not_confused_by_dlc_whitelist(self):
        from sff.linux.yaml_config import add_additional_app
        self.assertTrue(add_additional_app(self.config, "300"))
        value = yaml.safe_load(self.config.read_text())
        self.assertEqual(set(value["AdditionalApps"]), {100, 200, 300})
        self.assertEqual(value["AppIds"], [300])
        self.assertIs(value["SafeMode"], True)
        self.assertFalse(add_additional_app(self.config, "300"))

    def test_running_game_detection_does_not_count_installer(self):
        from ember.host import game_running
        class Process:
            def __init__(self, command):
                self.info = {"cmdline": command}
        with patch("ember.host.psutil.process_iter", return_value=[Process(["reaper", "SteamLaunch", "AppId=480", "Install=1"])]):
            self.assertFalse(game_running())
        with patch("ember.host.psutil.process_iter", return_value=[Process(["reaper", "SteamLaunch", "AppId=480"])]):
            self.assertTrue(game_running())

    def test_new_ntfs_prefix_uses_linux_but_existing_save_is_preserved(self):
        from ember.host import prepare_compatdata
        steam, library = self.root / "LinuxSteam", self.root / "WindowsLibrary"
        library.mkdir()
        with patch("ember.host.subprocess.run") as run:
            run.return_value.stdout = "ntfs3\n"
            self.assertTrue(prepare_compatdata(steam, library, "480"))
            self.assertEqual((library / "steamapps/compatdata/480").resolve(), steam / "steamapps/compatdata/480")
            original = library / "steamapps/compatdata/481"
            original.mkdir()
            (original / "save.dat").write_bytes(b"progress")
            self.assertFalse(prepare_compatdata(steam, library, "481"))
            self.assertEqual((original / "save.dat").read_bytes(), b"progress")


if __name__ == "__main__":
    unittest.main()
