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
import logging
import os
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path

import msgpack
from PyQt6.QtCore import QTimer

from ember.config import ROOT

PLUGIN_ID = "app.ember.bridge"
logger = logging.getLogger(__name__)


def mep_call(method, params=None):
    """Use Millennium's local Extension Protocol, with its MessagePack framing."""
    address = str(Path(os.environ["TEMP"]) / "millennium-mep.sock").encode("utf-8")
    if len(address) >= 108:
        raise ValueError("Millennium socket path is too long")
    with socket.socket(1, socket.SOCK_STREAM, 0) as client:
        if os.name == "nt":
            class UnixAddress(ctypes.Structure):
                _fields_ = [("family", ctypes.c_ushort), ("path", ctypes.c_char * 108)]
            endpoint = UnixAddress(1, address)
            winsock = ctypes.WinDLL("ws2_32", use_last_error=True)
            winsock.connect.argtypes = [ctypes.c_size_t, ctypes.c_void_p, ctypes.c_int]
            if winsock.connect(client.fileno(), ctypes.byref(endpoint), ctypes.sizeof(endpoint)):
                raise OSError("Cannot connect to Millennium Extension Protocol")
        else:
            client.connect(address.decode())
        client.settimeout(8)
        payload = msgpack.packb({"id": "ember", "method": method, "params": params or {}}, use_bin_type=True)
        client.sendall(struct.pack("<I", len(payload)) + payload)

        def receive(length):
            result = bytearray()
            while len(result) < length:
                part = client.recv(length - len(result))
                if not part:
                    raise ConnectionError("Millennium closed the connection")
                result.extend(part)
            return result

        length, = struct.unpack("<I", receive(4))
        if length > 64 * 1024 * 1024:
            raise ValueError("Invalid Millennium response length")
        return msgpack.unpackb(receive(length), raw=False)


def lua_literal(value):
    value = str(value)
    delimiter = "="
    while "]" + delimiter + "]" in value:
        delimiter += "="
    return "[" + delimiter + "[" + value + "]" + delimiter + "]"


def prepare_adapter(steam):
    target = steam / "millennium/plugins" / PLUGIN_ID
    (target / "backend").mkdir(parents=True, exist_ok=True)
    (target / ".millennium/Dist").mkdir(parents=True, exist_ok=True)
    metadata = {"name": PLUGIN_ID, "common_name": "Ember", "description": "Ember inside Steam", "version": __import__("ember").VERSION, "author": "Ember contributors", "backend": "backend", "backendType": "lua", "useBackend": True}
    from ember.launch import install_root
    metadata['ember_install_dir'] = str(install_root())
    (target / "plugin.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    from ember.launch import launch_command
    command = subprocess.list2cmdline(launch_command("--millennium-bootstrap"))
    if any(char in command for char in '%!&|<>^\r\n'):
        raise ValueError("Ember installation path contains unsupported shell characters")
    if os.name == "nt":
        command = '"' + command + '"'
    template = (ROOT / "ember/millennium/backend.lua").read_text(encoding="utf-8")
    data = Path(os.environ["LOCALAPPDATA"]) / "Ember/Desktop"
    template = template.replace("@COMMAND@", lua_literal(command)).replace("@DATA@", lua_literal(data))
    (target / "backend/main.lua").write_text(template, encoding="utf-8")
    source = (ROOT / "ember/millennium/frontend.js").read_text(encoding="utf-8")
    (target / ".millennium/Dist/index.js").write_text(source, encoding="utf-8")
    webkit = (ROOT / "ember/millennium/webkit.js").read_text(encoding="utf-8")
    (target / ".millennium/Dist/webkit.js").write_text(webkit, encoding="utf-8")
    return target


def remove_owned_adapter():
    import shutil
    from ember.launch import install_root
    from ember.config import steam_path
    os.environ['EMBER_MODE'] = 'desktop'
    try:
        steam = steam_path()
    except FileNotFoundError:
        logger.debug('Steam is not installed; no adapter to remove')
        return
    target = steam / 'millennium/plugins' / PLUGIN_ID
    metadata_path = target / 'plugin.json'
    if not metadata_path.is_file():
        return
    metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
    if metadata.get('ember_install_dir') != str(install_root()):
        logger.info('Keeping adapter owned by a different Ember installation')
        return
    from ember.desktop import steam_processes
    if steam_processes((steam / 'steam.exe').resolve()):
        raise RuntimeError('Close Steam before uninstalling its Ember adapter.')
    if target.is_symlink() or target.resolve().parent != (steam / 'millennium/plugins').resolve():
        raise ValueError('Invalid Ember adapter directory')
    shutil.rmtree(target)
    logger.info('Removed this installation’s optional Millennium adapter')


def install_adapter(steam):
    prepare_adapter(steam)
    result = mep_call("plugin.enable", {"name": PLUGIN_ID})
    if result.get("error"):
        raise RuntimeError("Millennium could not enable Ember: " + str(result["error"]))
    logger.info("Enabled Ember adapter through Millennium Extension Protocol")
    return result


class MillenniumIntegration:
    def __init__(self, server, data):
        self.server, self.data = server, data
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh)

    def refresh(self):
        try:
            connected = time.time() - (self.data / "millennium-heartbeat.txt").stat().st_mtime < 12
        except OSError:
            connected = False
        self.server.integration.update(connected=connected, mode="millennium", message="Подключено через Millennium" if connected else "Ожидание адаптера Millennium")

    def start(self):
        self.refresh()
        self.timer.start(2000)

    def stop(self):
        self.timer.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--install", type=Path, required=True)
    options = parser.parse_args()
    print(json.dumps(install_adapter(options.install), ensure_ascii=False))
