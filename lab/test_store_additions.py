# Ember — Copyright (C) 2026 Ember contributors.
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details (LICENSE).

import json
import unittest
import urllib.error
import urllib.request
import tempfile
from pathlib import Path
from unittest.mock import patch, Mock

from ember.store_additions import StoreAdditions
from ember.server import LocalServer
from ember.cdp import SteamIntegration


class StoreAdditionTests(unittest.TestCase):
    def test_invalid_app_ids_cannot_enter_queue(self):
        queue = StoreAdditions()
        for app_id in (None, 12, "", "0", "01", "1/2", "１２", "4294967296", "1;cmd"):
            self.assertFalse(queue.request(app_id, "Game")["success"])
        self.assertIsNone(queue.pending())

    def test_duplicate_clicks_share_request_and_other_games_do_not_replace_it(self):
        queue = StoreAdditions()
        first = queue.request("12", "Game")
        self.assertEqual(queue.request("12", "Other name"), first)
        self.assertEqual(queue.request("13", "Other game")["error"], "busy")
        self.assertEqual(queue.pending()["name"], "Game")
        copy = queue.pending()
        copy["app_id"] = "13"
        self.assertEqual(queue.pending()["app_id"], "12")

    def test_only_matching_acknowledgement_consumes_request(self):
        queue = StoreAdditions()
        key = queue.request("12", "Game")["request_id"]
        self.assertFalse(queue.acknowledge("unknown"))
        self.assertEqual(queue.status(key)["state"], "waiting")
        self.assertTrue(queue.acknowledge(key))
        self.assertTrue(queue.acknowledge(key))
        self.assertIsNone(queue.pending())
        self.assertEqual(queue.status(key)["state"], "opened")
        self.assertNotEqual(queue.request("12", "Game")["request_id"], key)

    def test_unopened_request_expires_without_being_applied(self):
        queue = StoreAdditions()
        with patch("ember.store_additions.time.time", return_value=100):
            key = queue.request("12", "Game")["request_id"]
        with patch("ember.store_additions.time.time", return_value=161):
            self.assertIsNone(queue.pending())
            self.assertEqual(queue.status(key)["state"], "expired")
            self.assertFalse(queue.acknowledge(key))

    def test_metadata_is_bounded_and_control_characters_removed(self):
        queue = StoreAdditions()
        queue.request("12", " Game\x00\n ")
        self.assertEqual(queue.pending()["name"], "Game")
        queue.acknowledge(queue.pending()["request_id"])
        queue.request("13", "a" * 513)
        self.assertEqual(queue.pending()["name"], "App 13")

    def test_local_endpoint_requires_token_and_same_origin(self):
        server = LocalServer(Mock(), Mock(), "fixture-token")
        server.start()
        try:
            for path in ("/api/store-add", "/api/store-add?request_id=unknown"):
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(server.origin + path)
                self.assertEqual(caught.exception.code, 401)
            body = json.dumps({"action": "request", "app_id": "12", "name": "Game"}).encode()
            for origin, status in (("https://store.steampowered.com", 403), ("https://untrusted.example", 403)):
                request = urllib.request.Request(server.origin + "/api/store-add", data=body, headers={"Authorization": "Bearer fixture-token", "Origin": origin})
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(request)
                self.assertEqual(caught.exception.code, status)
            request = urllib.request.Request(server.origin + "/api/store-add", data=body, headers={"Authorization": "Bearer fixture-token", "Origin": server.origin})
            with urllib.request.urlopen(request) as response:
                self.assertTrue(json.load(response)["success"])
        finally:
            server.shutdown()
            server.server_close()

    def test_store_discovery_requires_exact_steam_origin(self):
        for url in ("https://store.steampowered.com/app/12/", "https://store.steampowered.com/search/"):
            self.assertTrue(SteamIntegration._store_target({"url": url}))
        for url in ("http://store.steampowered.com/app/12", "https://store.steampowered.com.evil/app/12", "https://evil/?store.steampowered.com", "about:blank"):
            self.assertFalse(SteamIntegration._store_target({"url": url}))

    def test_adapter_files_can_be_prepared_without_touching_running_services(self):
        from ember.millennium import prepare_adapter
        with tempfile.TemporaryDirectory() as folder, patch("ember.millennium.mep_call", side_effect=AssertionError("Must not change a running plugin")):
            target = prepare_adapter(Path(folder))
            self.assertIn("__emberStore", (target / ".millennium/Dist/webkit.js").read_text(encoding="utf-8"))
            self.assertIn("store handoff v2", (target / ".millennium/Dist/index.js").read_text(encoding="utf-8"))
            self.assertNotIn("@COMMAND@", (target / "backend/main.lua").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
