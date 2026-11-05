# Ember — Copyright (C) 2026 Ember contributors.
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details (LICENSE).

import concurrent.futures
import json
import logging
import os
import queue
import threading
import time
import urllib.request
from urllib.parse import urlsplit

import websocket

from ember.config import ROOT

logger = logging.getLogger(__name__)


class CDPClient:
    def __init__(self, url, on_open, on_store=None):
        self.socket = websocket.create_connection(url, suppress_origin=True, timeout=5)
        self.socket.settimeout(1)
        self._send_lock = threading.Lock()
        self._pending = {}
        self._next_id = 0
        self.alive = True
        self.on_open = on_open
        self.on_store = on_store
        threading.Thread(target=self._read, daemon=True, name="ember-cdp-reader").start()

    def _read(self):
        while self.alive:
            try:
                raw = self.socket.recv()
                if not raw:
                    break
                payload = json.loads(raw)
                if "id" in payload:
                    future = self._pending.pop(payload["id"], None)
                    if future is not None and not future.done():
                        if "error" in payload:
                            future.set_exception(RuntimeError(payload["error"].get("message", "CDP error")))
                        else:
                            future.set_result(payload.get("result", {}))
                elif payload.get("method") == "Runtime.bindingCalled":
                    if payload.get("params", {}).get("name") == "__emberOpenPanel":
                        self.on_open()
                    elif payload.get("params", {}).get("name") == "__emberStoreBinding" and self.on_store:
                        self.on_store(payload["params"].get("payload", ""))
            except websocket.WebSocketTimeoutException:
                continue
            except Exception:
                logger.debug("Steam target disconnected", exc_info=True)
                break
        self.alive = False
        for future in list(self._pending.values()):
            if not future.done():
                future.set_exception(ConnectionError("Steam target closed"))
        self._pending.clear()

    def call(self, method, params=None, timeout=8):
        if not self.alive:
            raise ConnectionError("Steam target unavailable")
        future = concurrent.futures.Future()
        with self._send_lock:
            self._next_id += 1
            request_id = self._next_id
            self._pending[request_id] = future
            self.socket.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
        try:
            return future.result(timeout)
        finally:
            self._pending.pop(request_id, None)

    def evaluate(self, expression):
        result = self.call("Runtime.evaluate", {"expression": expression, "returnByValue": True})
        if "exceptionDetails" in result:
            details = result["exceptionDetails"]
            raise RuntimeError(details.get("exception", {}).get("description") or details.get("text", "Steam UI script failed"))
        return result.get("result", {}).get("value")

    def close(self):
        self.alive = False
        self.socket.close()


class SteamIntegration:
    def __init__(self, server, ports, allowed_origin=None, open_on_connect=False, on_open_panel=None):
        self.server = server
        self.ports = ports
        self.allowed_origin = allowed_origin
        self.open_on_connect = open_on_connect
        self.on_open_panel = on_open_panel
        self.on_before_open = None
        self.clients = {}
        self.commands = queue.Queue()
        self.running = True
        self.store_states = {}
        self.script = "\n".join((ROOT / name).read_text(encoding="utf-8") for name in
                                ("ember/web/library_stats.js", "ember/web/steam.js"))
        self._library_cache = (0, [])
        self.store_script = (ROOT / "ember/millennium/webkit.js").read_text(encoding="utf-8")

    def open_panel(self):
        self.commands.put("open")

    def show_embedded(self):
        self.commands.put("show_embedded")

    def start(self):
        threading.Thread(target=self._run, daemon=True, name="ember-steam").start()

    def _library_apps(self):
        if os.name == "nt" or self.allowed_origin is not None:
            return []
        checked, apps = self._library_cache
        if time.monotonic() - checked >= 15:
            from ember.config import steam_path, DATA
            from ember.library import Library
            apps = sorted(Library(steam_path(), DATA).registrations())
            self._library_cache = (time.monotonic(), apps)
        return apps

    def _inject(self, client):
        config = {"origin": self.server.origin, "token": self.server.token, "mode": "lab" if self.allowed_origin else "standalone", "nativeWindow": bool(self.on_open_panel)}
        if os.name != "nt" and self.allowed_origin is None:
            from ember.host import steam_ui_classes
            from ember.config import steam_path
            config.update(embedded=True, classes=steam_ui_classes(str(steam_path())),
                          libraryApps=self._library_apps())
        client.evaluate("window.__EMBER_CONFIG__=" + json.dumps(config) + ";\n" + self.script)

    @staticmethod
    def _store_target(target):
        url = urlsplit(target.get("url", ""))
        return url.scheme == "https" and url.netloc == "store.steampowered.com"

    def _store_call(self, key, raw):
        entry = self.clients.get(key)
        if not entry or entry[0] != "Ember Store" or len(raw) > 4096:
            return
        client = entry[1]
        request_id = None
        try:
            payload = json.loads(raw)
            request_id = payload.get("call_id")
            if type(request_id) is not int or not 0 < request_id < 2**53:
                raise ValueError("Invalid store call")
            args = payload.get("args", [])
            if payload.get("method") == "request_store_add" and isinstance(args, list) and len(args) == 2:
                current_id = client.evaluate("location.origin === 'https://store.steampowered.com' ? location.pathname.match(/^\\/app\\/([1-9]\\d{0,9})(?:\\/|$)/)?.[1] : null")
                if args[0] != current_id:
                    raise ValueError("Store page changed")
                result = self.server.store_additions.request(*args)
                if result.get("success"):
                    self.open_panel()
            elif payload.get("method") == "get_store_add_status" and isinstance(args, list) and len(args) == 1 and isinstance(args[0], str):
                result = self.server.store_additions.status(args[0])
            else:
                raise ValueError("Invalid store method")
            result["language"] = getattr(self.server, "language", "ru")
            response = {"call_id": request_id, "result": result}
        except Exception as error:
            logger.debug("Store handoff failed", exc_info=True)
            response = {"call_id": request_id, "error": str(error)}
        client.evaluate("window.__emberStoreReply?.(" + json.dumps(response) + ")")

    def _discover(self):
        for port in self.ports:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=1) as response:
                    targets = json.load(response)
                if self.allowed_origin is None and not any(target.get("title") == "SharedJSContext" and target.get("url", "").startswith("https://steamloopback.host/") for target in targets):
                    continue
                return [target for target in targets
                        if self._store_target(target) or (target.get("title") in ("Steam", "Steam Root Menu")
                        and (target.get("url", "").startswith(("https://steamloopback.host/", "about:blank?createflags=")) if self.allowed_origin is None else target.get("url", "").startswith(self.allowed_origin + "/lab/")))]
            except Exception:
                continue
        return []

    def _run(self):
        last_connected = None
        while self.running:
            targets = self._discover()
            live_ids = {target["id"] for target in targets}
            for key in list(self.clients):
                if key not in live_ids or not self.clients[key][1].alive:
                    self.clients.pop(key)[1].close()
            for target in targets:
                try:
                    expected = "Ember Store" if self._store_target(target) else target["title"]
                    previous = self.clients.get(target["id"])
                    if previous and previous[0] != expected:
                        self.clients.pop(target["id"])[1].close()
                        logger.info("Steam browser target changed role to %s; reconnecting", expected)
                    if target["id"] not in self.clients:
                        store = self._store_target(target)
                        client = CDPClient(target["webSocketDebuggerUrl"], self.open_panel, lambda raw, key=target["id"]: self.commands.put(("store", key, raw)))
                        client.call("Runtime.enable")
                        client.call("Runtime.addBinding", {"name": "__emberStoreBinding" if store else "__emberOpenPanel"})
                        self.clients[target["id"]] = ("Ember Store" if store else target["title"], client)
                        if store:
                            if not client.evaluate("!!window.__emberStore"): client.evaluate(self.store_script)
                        else: self._inject(client)
                        logger.info("Ember attached to %s", target["title"])
                    else:
                        client = self.clients[target["id"]][1]
                        if self._store_target(target):
                            if not client.evaluate("!!window.__emberStore"):
                                client.call("Runtime.addBinding", {"name": "__emberStoreBinding"})
                                client.evaluate(self.store_script)
                        elif client.evaluate("!!window.__emberSteam"):
                            client.evaluate("window.__EMBER_CONFIG__.libraryApps=" + json.dumps(self._library_apps()) + ";window.__emberSteam.refresh()")
                        else:
                            self._inject(client)
                            logger.info("Ember restored after Steam interface reload")
                    if self._store_target(target):
                        state = client.evaluate("JSON.stringify({app:location.pathname.match(/^\\/app\\/(\\d+)/)?.[1]||null,adapter:!!window.__emberStore,binding:typeof window.__emberStoreBinding==='function',purchase:!!document.querySelector('#game_area_purchase,.game_area_purchase'),button:!!document.getElementById('ember-store-add')})")
                        if state != self.store_states.get(target["id"]):
                            self.store_states[target["id"]] = state
                            logger.info("Steam store adapter state: %s", state)
                except Exception as error:
                    key = "error:" + target["id"]
                    if self.store_states.get(key) != str(error):
                        self.store_states[key] = str(error)
                        logger.warning("Could not attach Ember to Steam target %s: %s", target.get("title"), error)
            connected = any(title == "Steam" and client.alive for title, client in self.clients.values())
            self.server.integration.update({"connected": connected, "mode": "embedded" if os.name != "nt" and not self.allowed_origin else "standalone", "message": "Подключено к Steam" if connected else "Ожидание Steam с включённым интерфейсом разработки"})
            if connected != last_connected:
                logger.info("Steam integration connected=%s", connected)
                if connected and self.open_on_connect:
                    self.open_panel()
                last_connected = connected
            try:
                command = self.commands.get(timeout=1.5)
                if isinstance(command, tuple) and command[0] == "store":
                    self._store_call(command[1], command[2])
                    continue
                if command in ("open", "show_embedded"):
                    if self.on_open_panel:
                        self.on_open_panel()
                        continue
                    if command == "open" and self.on_before_open:
                        self.on_before_open()
                        continue
                    for title, client in list(self.clients.values()):
                        if title == "Steam" and client.alive:
                            client.evaluate("window.__emberSteam.open()")
                            break
            except queue.Empty:
                continue
            except Exception:
                logger.warning("Could not open Ember in Steam", exc_info=True)

    def stop(self):
        self.running = False
        for _, client in list(self.clients.values()):
            try:
                client.evaluate("window.__emberSteam?.dispose()")
                client.evaluate("window.__emberStore?.dispose()")
                client.close()
            except Exception:
                logger.debug("Steam target already closed during cleanup")
