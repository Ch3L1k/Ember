# Ember — Copyright (C) 2026 Ember contributors.
# SPDX-License-Identifier: GPL-3.0-or-later

import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import yaml
import vdf

from ember.linux_registration import add_to_library, write_native_keys, native_entries, restore_native_entries
from sff.gui.bridges.download_bridge import _bridge_run_linux_fastest


class LinuxRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.steam = self.root / "Steam"
        (self.steam / "config").mkdir(parents=True)
        (self.steam / "config/config.vdf").write_text(vdf.dumps({"InstallConfigStore": {"Software": {"Valve": {"Steam": {}}}}}, pretty=True))
        self.config = self.root / "config.yaml"
        self.config.write_text("SafeMode: true\nAdditionalApps:\n  - 123\nAppTokens:\nManifestIds:\n")
        self.lua = self.root / "480.lua"
        self.lua.write_text('addappid(480)\naddappid(481,1,"' + "a" * 64 + '")\n')
        self.events = []
        self.bridge = SimpleNamespace(
            _steam_path=self.steam, _api_key="", _installed_games_cache="old",
            download_progress=SimpleNamespace(emit=lambda raw: self.events.append(json.loads(raw))),
            _ui=SimpleNamespace(sls_man=SimpleNamespace(sls_config_path=self.config),
                                process_from_store=lambda **kw: self.fail("Content downloader called")))
        self.data_patch = patch("ember.linux_tools.DATA", self.root / "backups")
        self.data_patch.start()
        self.environment = patch.dict("os.environ", EMBER_MODE="desktop")
        self.environment.start()
        self.processes = patch("sff.core.processes.is_proc_running", return_value=False)
        self.processes.start()
        self.native = patch("ember.linux_registration.require_native_installer")
        self.native.start()
        self.keys = patch("ember.linux_registration.write_native_keys")
        self.keys.start()
        self.platform = patch("ember.platform_selection.ensure_registration_platform")
        self.platform.start()
        self.addCleanup(self.platform.stop)
        self.prefixes = patch("ember.platform_selection.prepare_registration_prefixes")
        self.prefixes.start()
        self.addCleanup(self.prefixes.stop)

    def tearDown(self):
        self.data_patch.stop()
        self.environment.stop()
        self.processes.stop()
        self.native.stop()
        self.keys.stop()
        self.temp.cleanup()

    def test_add_changes_metadata_without_installing_or_downloading_files(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(add_to_library(self.bridge, "480", "local", lua_path=self.lua))
        value = yaml.safe_load(self.config.read_text())
        self.assertEqual(value["AdditionalApps"], [123, 480])
        self.assertIs(value["SafeMode"], True)
        self.assertTrue((self.steam / "config/stplug-in/480.lua").is_file())
        self.assertFalse((self.steam / "steamapps").exists())
        self.assertEqual(self.events[-1]["status"], "Complete")
        self.assertFalse(any("Downloading depot" in event["status"] for event in self.events))

    def test_platform_failure_stops_before_registration_writes(self):
        before = self.config.read_bytes()
        with patch("ember.platform_selection.ensure_registration_platform", side_effect=ValueError("platform mismatch")):
            with self.assertRaisesRegex(ValueError, "platform mismatch"):
                add_to_library(self.bridge, "480", "local", lua_path=self.lua)
        self.assertEqual(self.config.read_bytes(), before)
        self.assertFalse((self.steam / "config/stplug-in").exists())
        self.assertFalse(any(event["status"] == "Complete" for event in self.events))

    def test_provider_add_only_fetches_registration_metadata(self):
        with patch("sff.lua.choices.download_lua_direct", return_value=self.lua) as fetch, contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(add_to_library(self.bridge, "480", "freelua"))
        fetch.assert_called_once()
        self.assertFalse((self.steam / "steamapps").exists())

    def test_mismatched_registration_cannot_modify_steam(self):
        before = self.config.read_bytes()
        self.lua.write_text('addappid(999)\naddappid(481,1,"' + "a" * 64 + '")\n')
        with self.assertRaises(ValueError):
            add_to_library(self.bridge, "480", "local", lua_path=self.lua)
        self.assertEqual(self.config.read_bytes(), before)
        self.assertFalse((self.steam / "config/stplug-in").exists())

    def test_desktop_route_cannot_fall_back_to_content_downloader(self):
        with patch.dict("os.environ", EMBER_MODE="desktop"), patch("ember.linux_registration.run_registration", return_value=True) as register:
            self.assertTrue(_bridge_run_linux_fastest(self.bridge, "480", "freelua"))
        register.assert_called_once_with(self.bridge, "480", "freelua", False)

    def test_missing_native_module_rejects_add_before_modifying_steam(self):
        before = self.config.read_bytes()
        with patch("ember.linux_registration.require_native_installer", side_effect=RuntimeError("not connected")):
            with self.assertRaises(RuntimeError):
                add_to_library(self.bridge, "480", "local", lua_path=self.lua)
        self.assertEqual(self.config.read_bytes(), before)
        self.assertFalse((self.steam / "config/stplug-in").exists())

    def test_native_metadata_roundtrip_keeps_other_games(self):
        from sff.lua.manager import parse_lua_contents
        target = self.root / "xdg/lumalinux/keys.txt"
        target.parent.mkdir(parents=True)
        target.write_text("99;\n100;99;0;0;" + "b" * 64 + "\n")
        with patch.dict("os.environ", XDG_CONFIG_HOME=str(self.root / "xdg")), patch("ember.config.DATA", self.root / "backups"):
            write_native_keys(parse_lua_contents(self.lua.read_text(), self.lua))
            owned = native_entries("480")
            self.assertEqual(set(owned), {"480", "481"})
            restore_native_entries(owned, False)
            self.assertFalse(native_entries("480"))
            self.assertTrue(native_entries("99"))
            restore_native_entries(owned, True)
            self.assertEqual(native_entries("480"), owned)


if __name__ == "__main__":
    unittest.main()
