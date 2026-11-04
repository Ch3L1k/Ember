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
import threading
import time
import unittest
import urllib.error
import urllib.request
import json
from unittest.mock import patch

from PyQt6.QtCore import QCoreApplication, QObject, pyqtSlot

from ember.rpc import Dispatcher, EventStream
from ember import desktop
from ember.server import LocalServer

application = QCoreApplication.instance() or QCoreApplication([])


class Counter(QObject):
    def __init__(self):
        super().__init__()
        self.count = 0

    @pyqtSlot()
    def increment(self):
        self.count += 1

    @pyqtSlot()
    def slow_increment(self):
        time.sleep(.04)
        self.count += 1


class RuntimeTests(unittest.TestCase):
    def test_expired_queued_action_never_executes(self):
        bridge = Counter()
        dispatcher = Dispatcher(bridge, EventStream())
        errors = []
        def invoke():
            try:
                dispatcher.call("increment", [], timeout=.01)
            except TimeoutError as error:
                errors.append(str(error))
        client = threading.Thread(target=invoke)
        client.start()
        client.join(timeout=2)
        self.assertFalse(client.is_alive())
        application.processEvents()
        self.assertEqual(bridge.count, 0)
        self.assertEqual(len(errors), 1)
        self.assertIn("не была запущена", errors[0])

    def test_started_action_completes_once_after_client_timeout(self):
        bridge = Counter()
        dispatcher = Dispatcher(bridge, EventStream())
        errors = []
        def invoke():
            try:
                dispatcher.call("slow_increment", [], timeout=.02)
            except TimeoutError as error:
                errors.append(str(error))
        client = threading.Thread(target=invoke)
        client.start()
        deadline = time.monotonic() + 2
        while client.is_alive() and time.monotonic() < deadline:
            application.processEvents()
            time.sleep(.001)
        client.join(timeout=1)
        self.assertEqual(bridge.count, 1)
        self.assertEqual(len(errors), 1)
        self.assertIn("ещё выполняется", errors[0])

    def test_event_stream_detects_evicted_history(self):
        stream = EventStream()
        for index in range(1600):
            stream.publish("progress", [index])
        gap = stream.read(0, timeout=0)
        self.assertTrue(gap["reset"])
        self.assertEqual(gap["events"], [])
        latest = stream.read(1599, timeout=0)
        self.assertFalse(latest["reset"])
        self.assertEqual(latest["events"][0]["args"], [1599])

    def test_cursor_from_previous_session_resets_without_waiting(self):
        stream = EventStream()
        with patch.object(stream._condition, "wait", side_effect=AssertionError("Must not wait for an obsolete cursor")):
            payload = stream.read(20)
        self.assertTrue(payload["reset"])
        self.assertEqual(payload["cursor"], 0)

    def test_subscription_starts_after_current_events(self):
        stream = EventStream()
        stream.publish("finished", ["old"])
        cursor = stream.cursor
        stream.publish("finished", ["new"])
        self.assertEqual([event["args"] for event in stream.read(cursor)["events"]], [["new"]])

    def test_running_desktop_launcher_reopens_existing_window(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = {"origin": "http://127.0.0.1:12345", "token": "test-only", "pid": os.getpid()}
            with patch.dict(os.environ, {"LOCALAPPDATA": folder}), patch("sys.argv", ["ember.desktop"]), patch.object(desktop, "live_runtime", return_value=runtime), patch.object(desktop, "request_action") as action, patch.object(desktop.logging, "basicConfig"):
                self.assertEqual(desktop.main(), 0)
                action.assert_called_once_with(runtime, "ember_open_window")

    def test_millennium_autostart_does_not_open_a_window(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ, {"LOCALAPPDATA": folder}), patch("sys.argv", ["ember.desktop", "--millennium", "--no-open"]), patch.object(desktop, "live_runtime", return_value={"integration": "millennium", "pid": os.getpid()}), patch.object(desktop, "request_action") as action, patch.object(desktop.logging, "basicConfig"):
                self.assertEqual(desktop.main(), 0)
                action.assert_not_called()

    def test_millennium_connection_requires_a_recent_adapter_heartbeat(self):
        from pathlib import Path
        from types import SimpleNamespace
        from ember.millennium import MillenniumIntegration
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder)
            server = SimpleNamespace(integration={})
            integration = MillenniumIntegration(server, data)
            integration.refresh()
            self.assertFalse(server.integration["connected"])
            heartbeat = data / "millennium-heartbeat.txt"
            heartbeat.write_text("fixture", encoding="utf-8")
            integration.refresh()
            self.assertTrue(server.integration["connected"])
            os.utime(heartbeat, (time.time() - 20, time.time() - 20))
            integration.refresh()
            self.assertFalse(server.integration["connected"])

    def test_http_timeout_is_reported_as_gateway_timeout(self):
        class WaitingDispatcher:
            def call(self, method, args):
                raise TimeoutError("Operation timed out")
        server = LocalServer(WaitingDispatcher(), EventStream(), "fixture-token")
        server.start()
        try:
            body = json.dumps({"method": "wait", "args": []}).encode()
            request = urllib.request.Request(server.origin + "/api/call", data=body,
                headers={"Authorization": "Bearer fixture-token", "Origin": server.origin, "Content-Type": "application/json"})
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(request, timeout=2)
            self.assertEqual(caught.exception.code, 504)
            self.assertEqual(json.loads(caught.exception.read())["error"], "Operation timed out")
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
