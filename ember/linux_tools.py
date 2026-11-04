# Ember — Copyright (C) 2026 Ember contributors.
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import logging
import os
import re
import threading
import shutil
import time
from pathlib import Path

import yaml

from ember.config import DATA

logger = logging.getLogger(__name__)
_lock = threading.RLock()


def config_path():
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "SLSsteam/config.yaml"


def read_config(path=None):
    path = Path(path) if path is not None else config_path()
    value = yaml.safe_load(path.read_text()) or {}
    if not isinstance(value, dict):
        raise ValueError("Неверный формат настроек SLSsteam")
    return path, value


def update_list(key, app_id, enabled, path=None):
    with _lock:
        return _update_list(key, app_id, enabled, path)


def _update_list(key, app_id, enabled, path=None):
    path, value = read_config(path)
    items = value.get(key) or []
    if not isinstance(items, list):
        raise ValueError("Неверный список " + key)
    original = path.read_bytes()
    had = str(app_id) in {str(item) for item in items}
    if had == enabled:
        return had
    items = [item for item in items if str(item) != str(app_id)]
    if enabled:
        items.append(int(app_id))
    value[key] = items
    backups = DATA / "sls-backups"
    backups.mkdir(parents=True, exist_ok=True)
    backup = backups / (str(time.time_ns()) + ".yaml")
    backup.write_bytes(original)
    if path.read_bytes() != original:
        raise RuntimeError("Настройки SLSsteam изменились. Повторите действие.")
    pending = path.with_suffix(".ember.tmp")
    text = yaml.safe_dump(value, sort_keys=False, allow_unicode=True)
    text = re.sub(r"(?m)^([A-Za-z][A-Za-z0-9]*): (?:null|\[\]|\{\})$", r"\1:", text)
    pending.write_text(text)
    pending.replace(path)
    logger.info("SLSsteam %s changed for app %s; backup %s", key, app_id, backup.name)
    return had


def run_tool(app_id, action):
    if not (Path.home() / ".local/share/SLSsteam/SLSsteam.so").is_file():
        raise RuntimeError("Сначала установите Linux-модуль Ember")
    path, value = read_config()
    record = DATA / "dlc-tools" / (str(app_id) + ".json")
    included = str(app_id) in {str(item) for item in value.get("AppIds") or []}
    managed = record.is_file()
    if action == "dlc_install" and not included:
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(json.dumps({"app_id": str(app_id), "previous": False}))
        update_list("AppIds", app_id, True)
        included = managed = True
    elif action == "dlc_remove":
        if not managed:
            raise ValueError("Эта настройка не была включена через Ember")
        update_list("AppIds", app_id, False)
        record.unlink()
        included = managed = False
    result = {"backend": "sls", "supported": True, "installed": included, "conflict": False,
              "api_files": 0, "restore_files": int(managed), "can_restore": managed}
    if action != "inspect":
        result["message"] = ("Доступ к DLC включён через Linux-модуль. Перезапустите игру. Отдельные файлы DLC при необходимости загрузите отдельно."
                             if included else "Настройка доступа к DLC отменена. Перезапустите игру.")
    return result
