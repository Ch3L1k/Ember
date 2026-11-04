# Ember — Copyright (C) 2026 Ember contributors.
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details (LICENSE).

import json
import logging
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
from ember.host import desktop_data

DATA = desktop_data()
DATA.mkdir(parents=True, exist_ok=True)


def _windows_steam_path():
    import winreg

    locations = (
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
    )
    for hive, key_path, value_name in locations:
        try:
            with winreg.OpenKey(hive, key_path) as key:
                raw = winreg.QueryValueEx(key, value_name)[0]
            if not isinstance(raw, str) or not raw.strip():
                logging.debug("Steam registry location is empty: %s/%s", key_path, value_name)
                continue
            candidate = Path(raw).resolve()
            if (candidate / "steam.exe").is_file():
                return candidate
            logging.debug("Steam registry location has no executable: %s", candidate)
        except (OSError, ValueError):
            logging.debug("Steam registry location is unavailable: %s/%s", key_path, value_name, exc_info=True)
    raise FileNotFoundError("Не удалось найти установленный Steam. Установите клиент Steam и повторите запуск Ember.")


def steam_path():
    selected = os.environ.get("EMBER_STEAM_DIR")
    if selected:
        return Path(selected).resolve()
    if os.environ.get("EMBER_MODE", "lab") != "desktop":
        raise RuntimeError("Ember Lab requires an explicit isolated Steam directory")
    if os.name == "nt":
        return _windows_steam_path()
    from ember.host import linux_steam_path
    return linux_steam_path()


def write_runtime(payload):
    target = DATA / "runtime.json"
    pending = target.with_suffix(".tmp")
    pending.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    pending.chmod(0o600)
    pending.replace(target)


def lab_mode():
    return os.environ.get("EMBER_MODE", "lab") == "lab"
