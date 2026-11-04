# Ember — Copyright (C) 2026 Ember contributors.
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details (LICENSE).

import tempfile
import unittest
from pathlib import Path

from sff.quick_tools.steam_updates import block_updates, prepare_for_millennium, unblock_updates


class SteamCompatibilityTests(unittest.TestCase):
    def test_blocker_is_archived_byte_for_byte_and_repeated_preflight_is_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            steam = Path(directory)
            content = b"# original\r\nBootStrapperInhibitAll=Enable\r\n"
            (steam / "steam.cfg").write_bytes(content)
            backup = prepare_for_millennium(steam, steam / "backups")
            self.assertEqual(backup.read_bytes(), content)
            self.assertFalse((steam / "steam.cfg").exists())
            self.assertIsNone(prepare_for_millennium(steam, steam / "backups"))

    def test_unknown_config_is_not_changed(self):
        with tempfile.TemporaryDirectory() as directory:
            steam = Path(directory)
            content = "OtherSetting=keep\nBootStrapperInhibitAll=Enable\n"
            (steam / "steam.cfg").write_text(content, encoding="utf-8")
            with self.assertRaises(ValueError):
                prepare_for_millennium(steam, steam / "backups")
            self.assertEqual((steam / "steam.cfg").read_text(encoding="utf-8"), content)

    def test_millennium_cannot_create_update_blocker(self):
        with tempfile.TemporaryDirectory() as directory:
            steam = Path(directory)
            library = steam / "millennium/lib/millennium.dll"
            library.parent.mkdir(parents=True)
            library.touch()
            with self.assertRaises(ValueError):
                block_updates(steam)
            self.assertFalse((steam / "steam.cfg").exists())

    def test_unblock_with_millennium_does_not_create_false_config(self):
        with tempfile.TemporaryDirectory() as directory:
            steam = Path(directory)
            library = steam / "millennium/lib/millennium.dll"
            library.parent.mkdir(parents=True)
            library.touch()
            (steam / "steam.cfg").write_text("BootStrapperInhibitAll=False\n", encoding="utf-8")
            unblock_updates(steam)
            self.assertFalse((steam / "steam.cfg").exists())
            self.assertEqual(len(list((steam / "millennium/config/ember-backups").glob("*.bak"))), 1)


if __name__ == "__main__":
    unittest.main()
