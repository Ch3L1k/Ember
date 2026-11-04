# Ember — Copyright (C) 2026 Ember contributors.
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details (LICENSE).

import argparse
import ctypes
import json
import os
import socket
import select
import struct
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import Mock

import msgpack

from ember.config import ROOT
from ember.millennium import lua_literal
from ember.rpc import EventStream
from ember.server import LocalServer


def run(binary, scratch, report):
    if os.name != "nt":
        raise RuntimeError("This check requires the Windows Millennium runtime")
    checks = []
    server = LocalServer(Mock(methods={}, signals={}), EventStream(), "fixture-native-lua")
    server.start()
    try:
        with tempfile.TemporaryDirectory(prefix="lua-", dir=scratch) as folder:
            folder = Path(folder)
            address = str(folder / "ipc.sock").encode()
            if len(address) >= 108:
                raise ValueError("The test socket path exceeds the Windows AF_UNIX limit")
            runtime = {"origin": server.origin, "token": server.token, "mode": "desktop", "language": "ru", "pid": 1}
            (folder / "runtime.json").write_text(json.dumps(runtime), encoding="utf-8")
            adapter = (ROOT / "ember/millennium/backend.lua").read_text(encoding="utf-8").replace("@COMMAND@", '"fixture"').replace("@DATA@", lua_literal(folder))
            (folder / "adapter.lua").write_text(adapter, encoding="utf-8")
            wrapper = '''local utils=require("utils")
local native_exec=utils.exec
function probe_exec(command)
 local output,code=native_exec(command)
 return {output=output,code=code}
end
utils.exec=function() return "",0 end
local http=require("http")
function probe_http_post(url)
 local result=http.post(url,'{"action":"request","app_id":"900000001","name":"Fixture"}',{headers={Authorization="Bearer fixture-native-lua"}})
 return result.status
end
return dofile(''' + lua_literal(folder / "adapter.lua") + ''')
'''
            (folder / "main.lua").write_text(wrapper, encoding="utf-8")
            class UnixAddress(ctypes.Structure):
                _fields_ = [("family", ctypes.c_ushort), ("path", ctypes.c_char * 108)]
            with socket.socket(1, socket.SOCK_STREAM, 0) as listener:
                winsock = ctypes.WinDLL("ws2_32", use_last_error=True)
                winsock.bind.argtypes = [ctypes.c_size_t, ctypes.c_void_p, ctypes.c_int]
                endpoint = UnixAddress(1, address)
                if winsock.bind(listener.fileno(), ctypes.byref(endpoint), ctypes.sizeof(endpoint)):
                    raise OSError("Could not bind the isolated Lua socket")
                listener.listen(1)
                listener.settimeout(10)
                with (folder / "stdout.log").open("wb") as log:
                    process = subprocess.Popen([str(binary), address.decode()], cwd=folder, stdin=subprocess.DEVNULL, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
                    try:
                        if not select.select([listener], [], [], 10)[0]:
                            raise TimeoutError("Isolated Lua runtime did not connect")
                        winsock.accept.argtypes = [ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
                        winsock.accept.restype = ctypes.c_size_t
                        accepted = winsock.accept(listener.fileno(), None, None)
                        if accepted == ctypes.c_size_t(-1).value:
                            raise OSError("Could not accept the isolated Lua connection")
                        connection = socket.socket(1, socket.SOCK_STREAM, 0, fileno=accepted)
                        with connection:
                            connection.settimeout(10)
                            def receive(length):
                                value = b""
                                while len(value) < length:
                                    chunk = connection.recv(length - len(value))
                                    if not chunk:
                                        raise ConnectionError("Isolated Lua runtime disconnected")
                                    value += chunk
                                return value
                            def send(payload):
                                data = msgpack.packb(payload, use_bin_type=True)
                                connection.sendall(struct.pack("<I", len(data)) + data)
                            def http_call(params):
                                if not params["url"].startswith(server.origin + "/"):
                                    raise AssertionError("Native Lua attempted to access a non-fixture URL")
                                body = params.get("data")
                                request = urllib.request.Request(params["url"], data=body.encode() if body else None, method=params.get("method", "GET"), headers=params.get("headers", {}))
                                try:
                                    response = urllib.request.urlopen(request, timeout=3)
                                except urllib.error.HTTPError as error:
                                    response = error
                                with response:
                                    return {"status": response.code, "body": response.read().decode(), "headers": {}}
                            def call(call_id, method, params):
                                send({"type": "req", "id": call_id, "method": method, "params": params})
                                while True:
                                    length, = struct.unpack("<I", receive(4))
                                    message = msgpack.unpackb(receive(length), raw=False)
                                    if message.get("type") == "res" and message.get("id") == call_id:
                                        if message.get("error"):
                                            raise RuntimeError(message["error"])
                                        return message["result"]
                                    if message.get("type") == "req":
                                        child_method = message["method"]
                                        result = http_call(message["params"]) if child_method == "http_request" else True if child_method in ("ready", "patches", "log") else {"error": "Unexpected fixture RPC: " + child_method}
                                        send({"type": "res", "id": message["id"], "result": result})
                            initialized = call(1, "init", {"plugin_name": "ember.fixture", "backend_dir": str(folder), "backend_file": str(folder / "main.lua"), "steam_path": str(folder), "steam_pid": 0})
                            assert initialized["ok"]
                            checks.append("Real Millennium Lua runtime starts with fixture files and process execution disabled")
                            def evaluate(sequence, method, args):
                                response = call(sequence, "evaluate", {"methodName": method, "argumentList": args})
                                if not response.get("success"):
                                    raise AssertionError(response.get("error", "Lua evaluation failed"))
                                return response.get("value")
                            probe = folder / "command path/probe file.cmd"
                            probe.parent.mkdir()
                            probe.write_text('@echo %~1\n@exit /b 0\n', encoding="ascii")
                            quoted = '"' + subprocess.list2cmdline([str(probe), "space argument"]) + '"'
                            executed = evaluate(19, "probe_exec", [quoted])
                            assert executed["code"] == 0 and executed["output"].strip() == "space argument", executed
                            checks.append("Native utils.exec preserves quoted paths and arguments containing spaces")
                            old_status = evaluate(2, "probe_http_post", [server.origin + "/api/store-add"])
                            assert str(old_status) == "401", old_status
                            checks.append("Native http.post loses authorization and reproduces the reported HTTP 401")
                            runtime["token"] = "expired-token"
                            (folder / "runtime.json").write_text(json.dumps(runtime), encoding="utf-8")
                            stale = evaluate(20, "get_connection", [])
                            assert stale.get("starting") and "origin" not in stale
                            runtime["token"] = server.token
                            (folder / "runtime.json").write_text(json.dumps(runtime), encoding="utf-8")
                            checks.append("Expired runtime credentials cannot produce a false ready connection")
                            first = evaluate(3, "request_store_add", ["900000001", "Ember Fixture"])
                            assert first["success"] and "token" not in first
                            checks.append("Patched adapter preserves POST body and authorization through native http.request")
                            state = evaluate(4, "get_connection", [])
                            assert state["add_request"]["app_id"] == "900000001"
                            assert state["add_request"]["name"] == "Ember Fixture"
                            checks.append("Real Lua FFI returns the matching queued game to the Steam frontend")
                            assert evaluate(5, "get_store_add_status", [first["request_id"]])["state"] == "waiting"
                            assert evaluate(6, "acknowledge_store_add", [first["request_id"]]) is True
                            assert evaluate(7, "get_store_add_status", [first["request_id"]])["state"] == "opened"
                            assert server.store_additions.pending() is None
                            checks.append("Opening acknowledgement consumes the same request and reports opened")
                            call(8, "shutdown", {})
                        process.wait(timeout=5)
                    finally:
                        if process.poll() is None:
                            process.terminate()
                            process.wait(timeout=5)
    finally:
        server.shutdown()
        server.server_close()
    payload = {"ok": True, "environment": "Separate Millennium Lua runtime and isolated authenticated HTTP server; no live Steam UI or game changes", "checks": checks}
    report.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "checks": len(checks), "original_http_post_status": old_status}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    run(args.binary.resolve(), args.scratch.resolve(), args.report.resolve())
