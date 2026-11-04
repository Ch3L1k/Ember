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
from unittest.mock import patch

from ember.workspace import Workspace


class WorkspaceTests(unittest.TestCase):
    def test_pins_and_searches_survive_new_backend_instance(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "workspace.json"
            workspace = Workspace(file)
            workspace.update({"action":"toggle_pin", "game":{"app_id":"123", "name":'Game "<test>"'}})
            workspace.update({"action":"remember_search", "query":"  hello   world  "})
            restored = Workspace(file).snapshot()
            self.assertEqual(restored["pins"][0]["name"], 'Game "<test>"')
            self.assertEqual(restored["searches"], ["hello world"])
            self.assertEqual(restored["revision"], 2)

    def test_search_history_is_deduplicated_and_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory) / "workspace.json")
            for index in range(12):
                workspace.update({"action":"remember_search", "query":str(index)})
            workspace.update({"action":"remember_search", "query":"HELLO"})
            workspace.update({"action":"remember_search", "query":"hello"})
            self.assertEqual(workspace.snapshot()["searches"][0], "hello")
            self.assertEqual(len(workspace.snapshot()["searches"]), 8)
            self.assertEqual(sum(query.casefold()=="hello" for query in workspace.snapshot()["searches"]), 1)

    def test_failed_write_preserves_file_and_in_memory_state(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "workspace.json"
            workspace = Workspace(file)
            workspace.update({"action":"remember_search", "query":"keep"})
            original = file.read_bytes()
            before = workspace.snapshot()
            with patch.object(Path, "replace", side_effect=OSError("fixture disk failure")):
                with self.assertRaises(OSError):
                    workspace.update({"action":"clear_searches"})
            self.assertEqual(file.read_bytes(), original)
            self.assertEqual(workspace.snapshot(), before)

    def test_addition_history_records_result_not_ownership(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory) / "workspace.json")
            workspace.update({"action":"note_game", "game":{"app_id":"123", "name":"Test"}})
            workspace.record({"task":"download_fastest", "app_id":"123", "success":False, "message":"offline"})
            workspace.record({"task":"download_fastest", "app_id":"123", "success":True})
            recent = Workspace(workspace.file).snapshot()["recent"]
            self.assertEqual(len(recent), 1)
            self.assertTrue(recent[0]["success"])
            self.assertEqual(recent[0]["name"], "Test")
            self.assertNotIn("owned", recent[0])

    def test_invalid_ids_and_unknown_actions_cannot_change_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory) / "workspace.json")
            for request in ({"action":"toggle_pin", "game":{"app_id":"../1"}}, {"action":"delete_files"}):
                with self.assertRaises(ValueError):
                    workspace.update(request)
            self.assertFalse(workspace.file.exists())


if __name__ == "__main__":
    unittest.main()
