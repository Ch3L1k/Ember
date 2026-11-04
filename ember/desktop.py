# Ember — Copyright (C) 2026 Ember contributors.
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details (LICENSE).

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import psutil


def read_json(url, timeout=2, token=None):
    request = urllib.request.Request(url, headers={"Authorization": "Bearer " + token} if token else {})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def live_runtime(data):
    try:
        payload = json.loads((data / "runtime.json").read_text(encoding="utf-8"))
        origin = payload.get("origin", "")
        if not isinstance(origin, str) or not re.fullmatch(r"http://127\.0\.0\.1:[0-9]{1,5}", origin) or not 0 < int(origin.rsplit(":", 1)[1]) <= 65535:
            return None
        if not isinstance(payload.get("token"), str) or not payload["token"]:
            return None
        if payload.get("mode") == "desktop" and read_json(origin + "/health", timeout=1).get("product") == "Ember" and read_json(origin + "/api/info", timeout=1, token=payload["token"]).get("mode") == "desktop":
            return payload
    except (OSError, ValueError, KeyError, AttributeError, TypeError):
        logging.debug("No active desktop backend", exc_info=True)
    return None


def request_action(runtime, method):
    body = json.dumps({"method": method, "args": []}).encode()
    request = urllib.request.Request(runtime["origin"] + "/api/call", data=body,
        headers={"Authorization": "Bearer " + runtime["token"], "Origin": runtime["origin"], "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=5) as response:
        response.read()


def request_quit(runtime):
    request_action(runtime, "ember_quit")
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            read_json(runtime["origin"] + "/health", timeout=.5)
        except (OSError, ValueError):
            return
        time.sleep(.1)
    raise RuntimeError("Ember ещё завершает работу. Дождитесь закрытия окна перед повторным запуском.")


def check_runtime_owner(runtime):
    try:
        running_executable = psutil.Process(int(runtime['pid'])).exe()
        current_executable = psutil.Process(os.getpid()).exe()
    except (psutil.Error, KeyError, ValueError, TypeError):
        logging.warning('Cannot identify the existing Ember installation', exc_info=True)
        raise RuntimeError('Не удалось определить запущенную установку Ember. Закройте Ember и повторите запуск.')
    running_path, current_path = Path(running_executable).resolve(), Path(current_executable).resolve()
    python_pair = os.name == 'nt' and {running_path.name.lower(), current_path.name.lower()} <= {'python.exe', 'pythonw.exe'} and running_path.parent == current_path.parent
    if running_path != current_path and not python_pair:
        raise RuntimeError('Запущена другая установка Ember. Закройте её через Stop Ember или полностью выйдите из Steam, затем запустите новый Ember.')


def steam_processes(executable):
    from ember.host import steam_processes as processes
    return processes(executable)


def supervise_backend(command, project, environment, data, steam_executable):
    restarts = 0
    while True:
        with open(data / "backend-console.log", "a", encoding="utf-8") as output:
            backend = subprocess.Popen(command, cwd=project, env=environment,
                stdin=subprocess.DEVNULL, stdout=output, stderr=output, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            started = time.monotonic()
            try:
                while backend.poll() is None:
                    if time.monotonic() - started > 60 and not steam_processes(steam_executable):
                        runtime = live_runtime(data)
                        if runtime:
                            request_quit(runtime)
                        break
                    time.sleep(2)
                backend.wait(timeout=15)
            finally:
                if backend.poll() is None:
                    backend.terminate()
                    backend.wait(timeout=5)
        if not backend.returncode or restarts >= 3 or not steam_processes(steam_executable):
            return backend.returncode
        restarts += 1
        logging.warning("Ember backend exited with code %s; restarting (%s/3)", backend.returncode, restarts)
        time.sleep(2 ** (restarts - 1))


def main():
    if os.name != "nt":
        from ember.linux_desktop import main as linux_main
        return linux_main()
    parser = argparse.ArgumentParser()
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--millennium", action="store_true")
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--attach", action="store_true")
    args = parser.parse_args()
    from ember.launch import install_root, launch_command
    project = install_root()
    data = Path(os.environ["LOCALAPPDATA"]) / "Ember/Desktop"
    data.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=data / "launcher.log", level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    existing = live_runtime(data)
    if args.stop:
        from ember.autostart import stop_watcher
        stop_watcher(data)
        if existing:
            request_quit(existing)
        return 0
    if existing:
        check_runtime_owner(existing)
        logging.info("Desktop backend is already running")
        if not args.no_open:
            request_action(existing, "ember_open_window")
        return 0
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    deadline = time.monotonic() + 8
    while True:
        ctypes.set_last_error(0)
        mutex = kernel.CreateMutexW(None, False, "Local\\EmberDesktopLauncher")
        if ctypes.get_last_error() != 183:
            break
        kernel.CloseHandle(mutex)
        existing = live_runtime(data)
        if existing:
            check_runtime_owner(existing)
            if not args.no_open:
                request_action(existing, "ember_open_window")
            return 0
        if time.monotonic() > deadline:
            raise RuntimeError("Ember ещё запускается или завершает работу. Повторите запуск через несколько секунд.")
        time.sleep(.2)
    if not mutex:
        raise OSError("Cannot acquire the Ember launcher lock")
    os.environ["EMBER_MODE"] = "desktop"
    from ember.config import steam_path
    steam = steam_path()
    executable = (steam / "steam.exe").resolve()
    if not executable.is_file():
        raise FileNotFoundError(executable)
    running = steam_processes(executable)
    millennium = args.millennium or (steam / "millennium/lib/millennium.dll").is_file()
    if args.attach and (not running or millennium):
        kernel.CloseHandle(mutex)
        return 0
    if not args.attach and not args.millennium:
        from ember.autostart import install
        install(steam, data)
    if millennium:
        from sff.quick_tools.steam_updates import prepare_for_millennium
        prepare_for_millennium(steam, data / "backups")
    if millennium and not args.millennium:
        # Millennium starts a launcher that must acquire this same lock.
        kernel.CloseHandle(mutex)
        from ember.millennium import install_adapter, mep_call
        if not running:
            subprocess.Popen([str(executable)], cwd=steam)
            deadline = time.monotonic() + 45
            while True:
                try:
                    mep_call("millennium.version")
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Millennium не запустился. Проверьте его установку в Steam.")
                    time.sleep(1)
            running = steam_processes(executable)
        try:
            install_adapter(steam)
        except OSError:
            ready = live_runtime(data)
            if not ready or ready.get("integration") != "millennium":
                raise
            logging.warning("Millennium enable acknowledgement failed after Ember became ready", exc_info=True)
        ready = live_runtime(data)
        if not ready:
            subprocess.Popen(launch_command("--millennium", "--no-open"), cwd=project,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        deadline = time.monotonic() + 45
        while not ready and time.monotonic() < deadline:
            time.sleep(.2)
            ready = live_runtime(data)
        if not ready:
            raise TimeoutError("Ember did not become ready. See bootstrap.log and startup-error.log.")
        check_runtime_owner(ready)
        if not args.no_open:
            request_action(ready, "ember_open_window")
        return 0
    try:
        targets = read_json("http://127.0.0.1:8080/json/list")
        debugging = bool(running) and any(target.get("title") == "SharedJSContext" and target.get("url", "").startswith("https://steamloopback.host/") for target in targets)
    except (OSError, ValueError):
        debugging = False
    if args.attach and not debugging:
        logging.info("Steam interface is not ready; automatic attachment deferred")
        kernel.CloseHandle(mutex)
        return 0
    if running and not debugging and not millennium:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                playing = winreg.QueryValueEx(key, "RunningAppID")[0]
        except FileNotFoundError:
            logging.debug("Steam has no current-user game activity entry", exc_info=True)
            playing = 0
        if playing:
            raise RuntimeError("Закрой игру и снова запусти Ember Steam. Клиент не был остановлен.")
        logging.info("Requesting normal Steam shutdown")
        subprocess.Popen([str(executable), "-shutdown"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        _, alive = psutil.wait_procs(running, timeout=35)
        if alive:
            raise RuntimeError("Steam ещё закрывается. Закрой клиент и снова запусти Ember Steam.")
    if not debugging and not millennium:
        logging.info("Starting Steam with its CEF debugging option")
        subprocess.Popen([str(executable), "-cef-enable-debugging"], cwd=steam)
    environment = dict(os.environ)
    environment.update(EMBER_MODE="desktop", EMBER_DATA_DIR=str(data), EMBER_STEAM_DIR=str(steam), EMBER_CDP_PORTS="8080", EMBER_OPEN_ON_CONNECT="0" if args.no_open else "1")
    if millennium:
        environment.update(EMBER_INTEGRATION="millennium", EMBER_CDP_PORTS="", EMBER_OPEN_ON_CONNECT="0")
        if not running:
            subprocess.Popen([str(executable)], cwd=steam)
        if not args.no_open:
            (data / "open-request.txt").write_text(str(time.time_ns()), encoding="utf-8")
    for key in ("EMBER_LAB_ROOT", "QTWEBENGINE_REMOTE_DEBUGGING", "QT_QPA_PLATFORM"):
        environment.pop(key, None)
    settings = data / "settings.bin"
    if not settings.exists():
        import msgpack
        from sff.core.structs import Settings
        settings.write_bytes(msgpack.packb({Settings.LANGUAGE.key_name: "ru", Settings.PLAY_MUSIC.key_name: False, Settings.PROVIDER_CONTRIBUTE_KEYS.key_name: False}))
    try:
        returncode = supervise_backend(launch_command("--backend"), project, environment, data, executable)
    finally:
        kernel.CloseHandle(mutex)
    if returncode:
        logging.error("Ember backend exited unexpectedly with code %s", returncode)
        raise RuntimeError("Ember завершился с ошибкой. Подробности: " + str(data / "backend-console.log"))
    return returncode


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        logging.exception("Desktop launch failed")
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, str(error), "Ember Steam", 16)
        raise
