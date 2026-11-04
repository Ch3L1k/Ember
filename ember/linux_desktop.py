# Ember — Copyright (C) 2026 Ember contributors.
# SPDX-License-Identifier: GPL-3.0-or-later

import argparse
import json
import logging
import os
import subprocess
import time
from pathlib import Path

import psutil

from ember.host import desktop_data, game_running, linux_lock, steam_command, steam_executable, steam_processes
from ember.launch import install_root, launch_command

logger = logging.getLogger(__name__)


def install(steam, data=None):
    data = Path(data or desktop_data())
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    marker = Path(steam) / ".cef-enable-remote-debugging"
    metadata = data / "autostart.json"
    try:
        previous = json.loads(metadata.read_text())
    except (OSError, ValueError):
        previous = {}
    owned = previous.get("steam") == str(steam) and previous.get("marker_owned") is True
    if not marker.exists():
        marker.touch(exist_ok=False)
        owned = True
    entry = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart/ember.desktop"
    entry.parent.mkdir(parents=True, exist_ok=True)
    command = launch_command("--watch-steam")
    entry.write_text("[Desktop Entry]\nType=Application\nName=Ember Steam integration\n"
                     "Exec=" + " ".join('"' + arg.replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$') + '"' for arg in command) +
                     "\nIcon=ember\nTerminal=false\nX-Ember-Owned=true\n")
    metadata.write_text(json.dumps({"steam": str(steam), "marker_owned": owned,
                                    "entry": str(entry), "command": command}))
    logger.info("Installed Linux desktop integration")
    subprocess.Popen(launch_command("--watch-steam"), cwd=install_root(), stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def uninstall():
    data = desktop_data()
    try:
        metadata = data / "autostart.json"
        payload = json.loads(metadata.read_text())
    except (OSError, ValueError):
        logger.debug("No Linux integration to remove", exc_info=True)
        return
    expected = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart/ember.desktop"
    if payload.get("command") != launch_command("--watch-steam"):
        raise RuntimeError("Интеграция принадлежит другой установке Ember")
    if expected.is_file() and "X-Ember-Owned=true" in expected.read_text():
        expected.unlink()
    marker = Path(payload["steam"]) / ".cef-enable-remote-debugging"
    if payload.get("marker_owned") and marker.is_file() and not marker.is_symlink() and marker.stat().st_size == 0:
        marker.unlink()
    metadata.unlink()


def stop_watcher(data=None):
    data = Path(data or desktop_data())
    data.mkdir(parents=True, exist_ok=True)
    (data / "watcher-stop.txt").write_text(str(time.time_ns()))
    watchers = []
    for process in psutil.process_iter(["cmdline"]):
        try:
            command = process.info["cmdline"] or []
            if process.pid != os.getpid() and "--watch-steam" in command and str(install_root() / "EmberRuntime.py") in command:
                watchers.append(process)
        except psutil.Error:
            logger.debug("Watcher process disappeared", exc_info=True)
    _, alive = psutil.wait_procs(watchers, timeout=5)
    if alive:
        logger.warning("A Steam watcher has not stopped yet")


def watch():
    os.environ["EMBER_MODE"] = "desktop"
    from ember.config import steam_path
    from ember.autostart import debug_ready
    from ember.desktop import live_runtime
    data = desktop_data()
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    logging.basicConfig(filename=data / "watcher.log", level=logging.INFO)
    with linux_lock(data / "watcher.lock") as acquired:
        if not acquired:
            return 0
        stop = data / "watcher-stop.txt"
        initial = stop.read_text() if stop.exists() else None
        child = None
        while (stop.read_text() if stop.exists() else None) == initial:
            if (child is None or child.poll() is not None) and not live_runtime(data) and steam_processes(steam_executable(steam_path())) and debug_ready():
                logger.info("Attaching Ember to Steam")
                child = subprocess.Popen(launch_command("--attach", "--no-open"), cwd=install_root(),
                                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(3)
    return 0


def main():
    parser = argparse.ArgumentParser()
    for flag in ("stop", "no-open", "attach", "standalone", "restart-steam", "millennium"):
        parser.add_argument("--" + flag, action="store_true")
    args = parser.parse_args()
    os.environ["EMBER_MODE"] = "desktop"
    data = desktop_data()
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.environ["EMBER_DATA_DIR"] = str(data)
    logging.basicConfig(filename=data / "launcher.log", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    from ember.config import steam_path
    from ember.desktop import live_runtime, request_action, request_quit, supervise_backend
    from ember.autostart import debug_ready
    if args.stop:
        stop_watcher(data)
        existing = live_runtime(data)
        if existing:
            request_quit(existing)
        return 0
    existing = live_runtime(data)
    if existing:
        if not args.no_open:
            request_action(existing, "ember_open_window")
        return 0
    with linux_lock(data / "launcher.lock", wait=15, ready=lambda: live_runtime(data)) as acquired:
        if not acquired:
            existing = live_runtime(data)
            if existing:
                if not args.no_open:
                    request_action(existing, "ember_open_window")
                return 0
            raise RuntimeError("Ember ещё запускается или закрывается. Повторите запуск через несколько секунд.")
        steam = steam_path()
        executable = steam_executable(steam)
        running = steam_processes(executable)
        ready = debug_ready()
        if args.attach and (not running or not ready):
            return 0
        install(steam, data)
        if args.restart_steam and running and not ready:
            if game_running():
                raise RuntimeError("Закройте запущенную игру перед перезапуском Steam. Игра не была остановлена.")
            subprocess.run(steam_command(steam, "-shutdown"), check=True, timeout=10)
            _, alive = psutil.wait_procs(running, timeout=40)
            if alive:
                raise RuntimeError("Steam ещё закрывается. Повторите запуск Ember позже.")
            running = []
        if not running and not args.standalone:
            subprocess.Popen(steam_command(steam, "-cef-enable-debugging"), cwd=steam,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if running and not ready:
            logger.info("Steam needs its next normal restart to expose the Ember menu; opening standalone window now")
        settings = data / "settings.bin"
        if not settings.exists():
            import msgpack
            from sff.core.structs import Settings
            settings.write_bytes(msgpack.packb({Settings.LANGUAGE.key_name: "ru", Settings.PLAY_MUSIC.key_name: False,
                                                Settings.PROVIDER_CONTRIBUTE_KEYS.key_name: False}))
        environment = dict(os.environ)
        environment.update(EMBER_MODE="desktop", EMBER_DATA_DIR=str(data), EMBER_STEAM_DIR=str(steam),
                           EMBER_CDP_PORTS="8080", EMBER_OPEN_ON_CONNECT="0" if args.no_open else "1",
                           EMBER_OPEN_STANDALONE="0" if args.no_open else "1")
        for key in ("EMBER_LAB_ROOT", "EMBER_INTEGRATION", "QTWEBENGINE_REMOTE_DEBUGGING"):
            environment.pop(key, None)
        result = supervise_backend(launch_command("--backend"), install_root(), environment, data, executable)
        if result:
            raise RuntimeError("Ember завершился с ошибкой. Журнал: " + str(data / "backend-console.log"))
        return result
