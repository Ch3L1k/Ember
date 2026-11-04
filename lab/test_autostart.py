# Ember — Copyright (C) 2026 Ember contributors.
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ember.autostart import attach_if_ready, install, uninstall


@unittest.skipUnless(os.name == "nt", "Windows integration")
class AutostartTests(unittest.TestCase):
    def test_no_steam_means_no_program_is_started(self):
        with tempfile.TemporaryDirectory() as folder, patch("ember.autostart.steam_processes", return_value=[]), \
                patch("ember.autostart.subprocess.Popen") as spawn:
            self.assertIsNone(attach_if_ready(Path(folder), Path(folder)))
            spawn.assert_not_called()

    def test_loading_steam_is_never_restarted_by_watcher(self):
        with tempfile.TemporaryDirectory() as folder, patch("ember.autostart.steam_processes", return_value=[Mock()]), \
                patch("ember.autostart.live_runtime", return_value=None), \
                patch("ember.autostart.debug_ready", return_value=False), patch("ember.autostart.subprocess.Popen") as spawn:
            self.assertIsNone(attach_if_ready(Path(folder), Path(folder)))
            spawn.assert_not_called()

    def test_ready_steam_gets_a_silent_attach_command(self):
        with tempfile.TemporaryDirectory() as folder, patch("ember.autostart.steam_processes", return_value=[Mock()]), \
                patch("ember.autostart.live_runtime", return_value=None), \
                patch("ember.autostart.debug_ready", return_value=True), \
                patch("ember.autostart.launch_command", return_value=["Ember.exe", "--attach", "--no-open"]), \
                patch("ember.autostart.subprocess.Popen") as spawn:
            self.assertIs(attach_if_ready(Path(folder), Path(folder)), spawn.return_value)
            self.assertEqual(spawn.call_args.args[0], ["Ember.exe", "--attach", "--no-open"])

    def test_healthy_backend_is_not_duplicated(self):
        with tempfile.TemporaryDirectory() as folder, patch("ember.autostart.steam_processes", return_value=[Mock()]), \
                patch("ember.autostart.live_runtime", return_value={"pid": 1}), patch("ember.autostart.subprocess.Popen") as spawn:
            self.assertIsNone(attach_if_ready(Path(folder), Path(folder)))
            spawn.assert_not_called()

    def test_millennium_keeps_its_own_startup_path(self):
        with tempfile.TemporaryDirectory() as folder, patch("ember.autostart.steam_processes", return_value=[Mock()]), \
                patch("ember.autostart.subprocess.Popen") as spawn:
            steam = Path(folder)
            library = steam / "millennium/lib/millennium.dll"
            library.parent.mkdir(parents=True)
            library.touch()
            self.assertIsNone(attach_if_ready(steam, steam))
            spawn.assert_not_called()

    def test_owned_marker_survives_reinstall_and_is_removed_on_uninstall(self):
        with tempfile.TemporaryDirectory() as folder, patch("winreg.CreateKey"), patch("winreg.SetValueEx"), \
                patch("winreg.OpenKey"), patch("winreg.QueryValueEx") as query, patch("winreg.DeleteValue"), \
                patch("ember.autostart.subprocess.Popen"):
            steam, data = Path(folder) / "Steam", Path(folder) / "Data"
            steam.mkdir()
            (steam / "steam.exe").touch()
            install(steam, data)
            install(steam, data)
            payload = json.loads((data / "autostart.json").read_text())
            self.assertTrue(payload["marker_owned"])
            query.return_value = (payload["command"], 1)
            uninstall(data)
            self.assertFalse((steam / ".cef-enable-remote-debugging").exists())

    def test_marker_created_by_another_tool_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder, patch("winreg.CreateKey"), patch("winreg.SetValueEx"), \
                patch("winreg.OpenKey"), patch("winreg.QueryValueEx") as query, patch("winreg.DeleteValue"), \
                patch("ember.autostart.subprocess.Popen"):
            steam, data = Path(folder) / "Steam", Path(folder) / "Data"
            steam.mkdir()
            (steam / "steam.exe").touch()
            marker = steam / ".cef-enable-remote-debugging"
            marker.touch()
            install(steam, data)
            payload = json.loads((data / "autostart.json").read_text())
            query.return_value = (payload["command"], 1)
            uninstall(data)
            self.assertTrue(marker.exists())


if __name__ == "__main__":
    unittest.main()
