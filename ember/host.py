# Ember — Copyright (C) 2026 Ember contributors.
# SPDX-License-Identifier: GPL-3.0-or-later

import contextlib
import logging
import os
import re
import functools
import shutil
import subprocess
import time
from pathlib import Path

import psutil

logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=4)
def steam_ui_classes(steam):
    try:
        source = (Path(steam) / "steamui/sp.js").read_text()
        classes = {}
        for key in ("SuperNavBar", "BottomBarContainer", "LocalContentContainer"):
            match = re.search(r'\b' + key + r':"([A-Za-z0-9_-]+)"', source)
            if match:
                classes[key] = match[1]
        navigation = re.search(r'SuperNav:"[A-Za-z0-9_-]+"[^{}]{0,1500}', source)
        if navigation:
            match = re.search(r'MenuButton:"([A-Za-z0-9_-]+)"', navigation[0])
            if match:
                classes["SuperNavButton"] = match[1]
        return classes
    except OSError:
        logger.debug("Using fallback Steam content geometry", exc_info=True)
        return {}


def desktop_data():
    if os.environ.get("EMBER_DATA_DIR"):
        return Path(os.environ["EMBER_DATA_DIR"]).expanduser().resolve()
    if os.name == "nt":
        return Path(os.environ["LOCALAPPDATA"]) / "Ember/Desktop"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "ember/Desktop"


def linux_steam_path():
    candidates = (Path.home() / ".local/share/Steam", Path.home() / ".steam/steam",
                  Path.home() / ".steam/root", Path.home() / ".steam/debian-installation",
                  Path.home() / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
                  Path.home() / ".var/app/com.valvesoftware.Steam/.steam/steam")
    for candidate in candidates:
        if (candidate / "steam.sh").is_file() or (candidate / "ubuntu12_32/steam").is_file():
            return candidate.resolve()
    raise FileNotFoundError("Steam не найден. Установите и запустите Steam перед Ember.")


def steam_executable(steam):
    return (Path(steam) / ("steam.exe" if os.name == "nt" else "ubuntu12_32/steam")).resolve()


def steam_command(steam, *args):
    if os.name == "nt":
        return [str(steam_executable(steam)), *args]
    if "com.valvesoftware.Steam" in Path(steam).parts:
        return ["flatpak", "run", "com.valvesoftware.Steam", *args]
    launcher = shutil.which("steam")
    if not launcher:
        raise FileNotFoundError("Команда steam не найдена в PATH")
    return [launcher, *args]


def steam_processes(executable):
    result = []
    for process in psutil.process_iter(["name", "exe"]):
        try:
            if process.info["name"].lower() in {"steam", "steam.exe"} and Path(process.info["exe"]).resolve() == Path(executable).resolve():
                result.append(process)
        except (psutil.Error, OSError, TypeError, AttributeError):
            logger.debug("Could not inspect Steam process", exc_info=True)
    return result


def game_running():
    for process in psutil.process_iter(["cmdline"]):
        try:
            command = process.info["cmdline"] or []
            if "SteamLaunch" in command and "Install=1" not in command:
                return True
        except psutil.Error:
            logger.debug("Game process disappeared", exc_info=True)
    return False


def prepare_compatdata(steam, library, app_id):
    app_id = str(app_id)
    if not app_id.isascii() or not app_id.isdigit():
        raise ValueError("Invalid App ID")
    steam, library = Path(steam).resolve(), Path(library).resolve()
    if steam == library:
        return False
    result = subprocess.run(["findmnt", "-n", "-o", "FSTYPE", "-T", str(library)],
                            capture_output=True, text=True, timeout=2)
    if result.stdout.strip() not in {"ntfs", "ntfs3", "fuseblk"}:
        return False
    source = library / "steamapps/compatdata" / app_id
    if source.is_symlink():
        return False
    if source.exists():
        logger.warning("Keeping the existing prefix for app %s; a shared Windows filesystem may need a separate prefix repair", app_id)
        return False
    target = steam / "steamapps/compatdata" / app_id
    target.mkdir(parents=True, exist_ok=True)
    source.parent.mkdir(parents=True, exist_ok=True)
    source.symlink_to(target, target_is_directory=True)
    logger.info("New Proton prefix for app %s routed to the Linux Steam directory", app_id)
    return True


@contextlib.contextmanager
def linux_lock(path, wait=0, ready=None):
    import fcntl
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("a") as handle:
        deadline = time.monotonic() + wait
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline or (ready and ready()):
                    yield False
                    return
                time.sleep(.2)
        try:
            handle.seek(0)
            handle.truncate()
            handle.write(str(os.getpid()))
            handle.flush()
            yield True
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
