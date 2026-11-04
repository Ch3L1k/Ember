# Ember — Copyright (C) 2026 Ember contributors.
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details (LICENSE).

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from ember.tools import inspect_game, run_tool


class ToolTests(unittest.TestCase):
    def setUp(self):
        platform = patch("ember.tools.os", SimpleNamespace(name="nt", walk=os.walk))
        platform.start()
        self.addCleanup(platform.stop)

    def test_fixture_install_and_remove_restore_original_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game, package = root / "game", root / "package"
            game.mkdir(); package.mkdir()
            original = game / "steam_api64.dll"
            original.write_bytes(b"fixture original")
            (game / "unrelated.txt").write_text("keep", encoding="utf-8")
            (package / "smoke_api64.dll").write_bytes(b"fixture replacement; never executed")
            bridge = SimpleNamespace(_resolve_acf=lambda _: SimpleNamespace(path=game))
            with patch("psutil.process_iter", return_value=[]), patch("sff.dlc_unlockers.downloader.GitHubReleaseDownloader") as downloader:
                downloader.return_value.download_latest = AsyncMock(return_value=package)
                self.assertTrue(run_tool(bridge, "900000001", "dlc_install")["installed"])
                self.assertEqual((game / "steam_api64_o.dll").read_bytes(), b"fixture original")
                self.assertFalse(run_tool(bridge, "900000001", "dlc_remove")["installed"])
                self.assertEqual(original.read_bytes(), b"fixture original")
                self.assertEqual((game / "unrelated.txt").read_text(), "keep")

    def test_existing_modification_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            game = Path(directory)
            (game / "steam_api64.dll").write_bytes(b"existing mod")
            (game / "steam_api64_o.dll").write_bytes(b"original")
            bridge = SimpleNamespace(_resolve_acf=lambda _: SimpleNamespace(path=game))
            with patch("psutil.process_iter", return_value=[]):
                with self.assertRaisesRegex(ValueError, "модификация"):
                    run_tool(bridge, "900000001", "dlc_install")
            self.assertEqual((game / "steam_api64.dll").read_bytes(), b"existing mod")

    def test_running_game_cannot_be_modified(self):
        with tempfile.TemporaryDirectory() as directory:
            game = Path(directory)
            (game / "steam_api64.dll").write_bytes(b"original")
            bridge = SimpleNamespace(_resolve_acf=lambda _: SimpleNamespace(path=game))
            with patch("psutil.process_iter", return_value=[SimpleNamespace(info={"exe":str(game / "game.exe")})]):
                with self.assertRaisesRegex(ValueError, "Закройте игру"):
                    run_tool(bridge, "900000001", "dlc_install")

    def test_unsupported_game_is_reported_without_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            game = Path(directory)
            self.assertFalse(inspect_game(game)["supported"])
            self.assertEqual(list(game.iterdir()), [])

    def test_installed_marker_without_original_files_cannot_claim_restoration(self):
        with tempfile.TemporaryDirectory() as directory:
            game = Path(directory)
            (game / "steam_api64.dll").write_bytes(b"fixture mod")
            (game / "SmokeAPI.config.json").write_text("{}", encoding="utf-8")
            state = inspect_game(game)
            self.assertTrue(state["installed"])
            self.assertFalse(state["can_restore"])
            self.assertEqual(state["restore_files"], 0)


if __name__ == "__main__":
    unittest.main()
