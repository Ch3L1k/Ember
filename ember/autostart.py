# Ember — Copyright (C) 2026 Ember contributors.
# SPDX-License-Identifier: GPL-3.0-or-later

import ctypes
import json
import logging
import os
import subprocess
import time
from pathlib import Path

from ember.desktop import live_runtime, read_json, steam_processes
from ember.launch import install_root, launch_command


def data_dir():
    from ember.host import desktop_data
    return desktop_data()


def debug_ready():
    try:
        targets = read_json("http://127.0.0.1:8080/json/list", timeout=1)
        return any(target.get("title") == "SharedJSContext" and
                   target.get("url", "").startswith("https://steamloopback.host/") for target in targets)
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def install(steam, data=None):
    if os.name != "nt":
        from ember import linux_desktop
        return linux_desktop.install(steam, data)
    import winreg

    data = data or data_dir()
    data.mkdir(parents=True, exist_ok=True)
    steam = Path(steam).resolve()
    if not (steam / "steam.exe").is_file():
        raise FileNotFoundError(steam / "steam.exe")
    metadata = data / "autostart.json"
    try:
        previous = json.loads(metadata.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = {}
    marker = steam / ".cef-enable-remote-debugging"
    owned = previous.get("steam") == str(steam) and previous.get("marker_owned") is True
    if not (steam / "millennium/lib/millennium.dll").is_file() and not marker.exists():
        with marker.open("x", encoding="utf-8"):
            pass
        owned = True
        logging.info("Enabled Steam's persistent local interface endpoint")
    command = subprocess.list2cmdline(launch_command("--watch-steam"))
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
        winreg.SetValueEx(key, "Ember", 0, winreg.REG_SZ, command)
    metadata.write_text(json.dumps({"steam": str(steam), "marker_owned": owned, "command": command}), encoding="utf-8")
    subprocess.Popen(launch_command("--watch-steam"), cwd=install_root(), stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)


def stop_watcher(data=None):
    if os.name != "nt":
        from ember import linux_desktop
        return linux_desktop.stop_watcher(data)
    data = data or data_dir()
    data.mkdir(parents=True, exist_ok=True)
    (data / "watcher-stop.txt").write_text(str(time.time_ns()), encoding="utf-8")
    import psutil
    own_executable = psutil.Process().exe()
    watchers = []
    for process in psutil.process_iter(["exe", "cmdline"]):
        try:
            if process.info["exe"] == own_executable and "--watch-steam" in (process.info["cmdline"] or []):
                watchers.append(process)
        except psutil.Error:
            logging.debug("Cannot inspect watcher during shutdown", exc_info=True)
    _, alive = psutil.wait_procs(watchers, timeout=8)
    if alive:
        raise RuntimeError("Фоновый процесс Ember ещё завершает работу. Повторите через несколько секунд.")


def uninstall(data=None):
    if os.name != "nt":
        from ember import linux_desktop
        return linux_desktop.uninstall()
    import winreg

    data = data or data_dir()
    metadata = data / "autostart.json"
    if not metadata.is_file():
        return
    payload = json.loads(metadata.read_text(encoding="utf-8"))
    command = subprocess.list2cmdline(launch_command("--watch-steam"))
    if payload.get("command") != command:
        logging.warning("Keeping automatic integration owned by another installation")
        return
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
            if winreg.QueryValueEx(key, "Ember")[0] == command:
                winreg.DeleteValue(key, "Ember")
    except FileNotFoundError:
        logging.debug("Ember startup entry is already absent")
    marker = Path(payload["steam"]) / ".cef-enable-remote-debugging"
    if payload.get("marker_owned") is True and marker.is_file() and not marker.is_symlink() and marker.stat().st_size == 0:
        marker.unlink()
    metadata.unlink()


def attach_if_ready(steam, data):
    if not steam_processes((steam / "steam.exe").resolve()):
        return None
    if (steam / "millennium/lib/millennium.dll").is_file() or live_runtime(data) or not debug_ready():
        return None
    logging.info("Steam started; attaching Ember")
    return subprocess.Popen(launch_command("--attach", "--no-open"), cwd=install_root(), stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)


def main():
    if os.name != "nt":
        from ember import linux_desktop
        return linux_desktop.watch()
    from ctypes import wintypes
    from ember.config import steam_path

    data = data_dir()
    data.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=data / "watcher.log", level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    ctypes.set_last_error(0)
    mutex = kernel.CreateMutexW(None, False, "Local\\EmberSteamWatcher")
    duplicate = ctypes.get_last_error() == 183
    if not mutex:
        raise OSError("Cannot acquire the Ember watcher lock")
    if duplicate:
        kernel.CloseHandle(mutex)
        return 0
    try:
        os.environ["EMBER_MODE"] = "desktop"
        steam = steam_path()
        stop_file = data / "watcher-stop.txt"
        initial_stop = stop_file.read_text() if stop_file.exists() else None
        child = None
        logging.info("Watching for ordinary Steam launches")
        while True:
            current_stop = stop_file.read_text() if stop_file.exists() else None
            if current_stop != initial_stop:
                return 0
            if child is None or child.poll() is not None:
                try:
                    child = attach_if_ready(steam, data)
                except (OSError, ValueError):
                    logging.warning("Could not attach Ember; will retry", exc_info=True)
            time.sleep(3)
    finally:
        kernel.CloseHandle(mutex)
