# Ember — Copyright (C) 2026 Ember contributors.
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details (LICENSE).

import asyncio
import logging
import os
from pathlib import Path

from ember.config import DATA

logger = logging.getLogger(__name__)


def inspect_game(folder):
    folder = Path(folder).resolve()
    api, installed, conflict, backups = False, False, False, False
    locations, configs, original_files = 0, set(), []
    for directory, _, files in os.walk(folder, followlinks=False):
        names = {name.lower() for name in files}
        api |= bool(names & {"steam_api.dll", "steam_api64.dll"})
        installed |= "smokeapi.config.json" in names
        conflict |= "cream_api.ini" in names
        backups |= bool(names & {"steam_api_o.dll", "steam_api64_o.dll"})
        locations += len(names & {"steam_api.dll", "steam_api64.dll"})
        if "smokeapi.config.json" in names:
            configs.add(Path(directory))
        for name in ("steam_api_o.dll", "steam_api64_o.dll"):
            if name in names:
                original_files.append(Path(directory))
    conflict |= backups and not installed
    restore_count = sum(parent in configs for parent in original_files)
    return {"supported": api, "installed": installed, "conflict": conflict, "api_files": locations, "restore_files": restore_count, "can_restore": installed and restore_count > 0}


def run_tool(bridge, app_id, action):
    if not str(app_id).isdigit():
        raise ValueError("Выберите установленную игру")
    if action in ("diagnose", "repair_launch"):
        from ember.diagnostics import run
        return run(bridge, app_id, repair=action == "repair_launch")
    game = bridge._resolve_acf(str(app_id))
    if game is None or not game.path.is_dir():
        raise ValueError("Установленная игра не найдена. Обновите список игр.")
    folder = game.path.resolve()
    logger.info("Ember tool %s started for app %s", action, app_id)
    if os.name != "nt":
        from ember.linux_tools import run_tool as linux_tool
        return linux_tool(app_id, action)
    state = inspect_game(folder)
    if action == "inspect":
        return state
    if action not in ("dlc_install", "dlc_remove"):
        raise ValueError("Неизвестный инструмент")
    import psutil
    for process in psutil.process_iter(["exe"]):
        try:
            if process.info["exe"] and Path(process.info["exe"]).resolve().is_relative_to(folder):
                raise ValueError("Закройте игру перед изменением её файлов.")
        except (psutil.Error, OSError):
            continue
    from sff.dlc_unlockers.smokeapi import SmokeAPIUnlocker
    unlocker = SmokeAPIUnlocker()
    if action == "dlc_install":
        if not state["supported"]:
            raise ValueError("В этой игре не найден поддерживаемый Steam API.")
        if state["conflict"]:
            raise ValueError("Обнаружена другая модификация Steam API. Сначала удалите её средствами, которыми она была установлена.")
        if not state["installed"]:
            from sff.dlc_unlockers.downloader import GitHubReleaseDownloader
            from sff.dlc_unlockers.base import UnlockerType
            source = asyncio.run(GitHubReleaseDownloader(DATA / "dlc-unlocker-cache").download_latest(UnlockerType.SMOKEAPI))
            if not source:
                raise RuntimeError("Не удалось загрузить SmokeAPI. Проверьте интернет и повторите попытку.")
            if not unlocker.install(folder, [], int(app_id), smokeapi_dir=source):
                raise RuntimeError("Не удалось установить SmokeAPI. Подробности сохранены в журнале Ember.")
        message = "SmokeAPI установлен. Перезапустите игру; Steam перезапускать не требуется. Отдельные файлы DLC при необходимости устанавливаются через Steam."
    else:
        if not state["installed"]:
            raise ValueError("Установка SmokeAPI в этой игре не обнаружена.")
        from sff.dlc_unlockers.smokeapi import InstallLocation
        locations = []
        for config in folder.rglob(unlocker.CONFIG_FILENAME):
            for name, architecture in (("steam_api.dll", "32"), ("steam_api64.dll", "64")):
                if (config.parent / (name[:-4] + "_o.dll")).is_file():
                    locations.append(InstallLocation(config.parent, name, architecture))
        if not locations or not all(unlocker._uninstall_from_location(location, folder) for location in locations):
            raise RuntimeError("Не удалось полностью восстановить исходные файлы. Проверьте журнал Ember.")
        message = "SmokeAPI удалён, исходные файлы восстановлены из резервных копий."
    result = inspect_game(folder)
    if result["installed"] != (action == "dlc_install"):
        raise RuntimeError("Проверка результата не подтвердила изменение файлов.")
    result["message"] = message
    return result
