# Ember — Copyright (C) 2026 Ember contributors.
# SPDX-License-Identifier: GPL-3.0-or-later

"""Register Steam library entries without running a content downloader."""

import json
import logging
import re
import os
import time
import tempfile
import threading
from functools import wraps
from pathlib import Path

from ember.library import Library

logger = logging.getLogger(__name__)


_METADATA_LOCK = threading.RLock()


def _serialized(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with _METADATA_LOCK:
            return function(*args, **kwargs)
    return wrapped


def _publish_metadata(target, text, original):
    fd, name = tempfile.mkstemp(prefix='.ember-keys-', dir=target.parent)
    pending = Path(name)
    try:
        with os.fdopen(fd, 'w') as handle:
            handle.write(text)
        if (target.read_text() if target.exists() else '') != original:
            raise RuntimeError("Данные нативной установки изменились. Повторите действие.")
        pending.replace(target)
    finally:
        pending.unlink(missing_ok=True)


def require_native_installer():
    import psutil
    candidates = [Path(os.environ.get("XDG_RUNTIME_DIR", "/run/user/" + str(os.getuid()))) / "lumalinux/status.json",
                  Path.home() / ".cache/lumalinux/status.json"]
    for candidate in candidates:
        try:
            status = json.loads(candidate.read_text())
            process = psutil.Process(int(status["pid"]))
            if process.name() != "steam" or status.get("blocked") or candidate.stat().st_mtime + 2 < process.create_time():
                continue
            if all(status.get("hooks", {}).get(name) == "installed" for name in ("DepotKey", "PackageZeroFinder")):
                return
        except (OSError, ValueError, KeyError, psutil.Error):
            continue
    raise RuntimeError("Нативная установка через Steam не подключена. Добавление остановлено: требуется рабочий модуль lumalinux.")


@_serialized
def native_entries(app_id):
    target = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "lumalinux/keys.txt"
    if not target.is_file():
        return {}
    result = {}
    for line in target.read_text().splitlines():
        parts = line.strip().split(";")
        if parts[0] == str(app_id) or (len(parts) == 5 and parts[1] == str(app_id)):
            result[parts[0]] = line
    return result


@_serialized
def restore_native_entries(entries, enabled):
    if not entries:
        return
    target = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "lumalinux/keys.txt"
    original = target.read_text() if target.exists() else ""
    lines = original.splitlines()
    for depot, entry in entries.items():
        current = next((line for line in lines if line.split(";", 1)[0] == str(depot)), None)
        if current is not None and current != entry:
            raise ValueError("Регистрация нативного модуля изменилась. Повторите действие.")
        lines = [line for line in lines if line.split(";", 1)[0] != str(depot)]
        if enabled:
            lines.append(entry)
    target.parent.mkdir(parents=True, exist_ok=True)
    _publish_metadata(target, "\n".join(lines) + "\n", original)


@_serialized
def write_native_keys(parsed):
    from ember.config import DATA
    target = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "lumalinux/keys.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    previous = target.read_text() if target.exists() else ""
    entries = {}
    for line in previous.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(";")
        if not parts[0].isdigit() or len(parts) not in (2, 5):
            raise ValueError("Неверный формат keys.txt модуля lumalinux")
        entries[parts[0]] = line
    app_id = str(parsed.app_id)
    entries[app_id] = app_id + ";"
    for pair in parsed.depots:
        if not pair.decryption_key:
            continue
        depot = str(pair.depot_id)
        if depot == app_id:
            entries[depot] = depot + ";" + pair.decryption_key
        else:
            manifest = str((parsed.manifest_overrides or {}).get(depot, "0"))
            entries[depot] = ";".join((depot, app_id, manifest, "0", pair.decryption_key))
    if previous:
        backups = DATA / "sls-backups"
        backups.mkdir(parents=True, exist_ok=True)
        (backups / (str(time.time_ns()) + "-native-keys.txt")).write_text(previous)
    _publish_metadata(target, "# Ember native Steam installation metadata\n" + "\n".join(entries[key] for key in sorted(entries, key=int)) + "\n", previous)
    logger.info("Native Steam metadata written for app %s", app_id)


def run_registration(bridge, app_id, source="", request_update=False, **options):
    try:
        return add_to_library(bridge, app_id, source, request_update, **options)
    except Exception as error:
        logger.exception("Linux library registration failed for %s", app_id)
        bridge.download_progress.emit(json.dumps({"app_id": app_id, "status": "Error: " + str(error), "progress": 0, "error": True}))
        return False


def add_to_library(bridge, app_id, source="", request_update=False, lua_path="", branch="", file_type=""):
    from sff.core.structs import LuaEndpoint
    from sff.lua.manager import parse_lua_contents
    from sff.lua.writer import ConfigVDFWriter
    from sff.steam_tools_compat import install_lua_to_steam
    from sff.linux.yaml_config import add_app_token, add_manifest_id
    from ember.linux_tools import read_config, update_list

    app_id = Library.app_id(str(app_id))
    require_native_installer()
    manager = getattr(bridge._ui, "sls_man", None)
    if manager is None:
        raise ValueError("Linux-модуль Ember не подключён")
    config = manager.sls_config_path
    read_config(config)

    def progress(status, percent=0):
        bridge.download_progress.emit(json.dumps({"app_id": app_id, "status": status, "progress": percent}))

    logger.info("Registering Linux Steam library entry %s without downloading content", app_id)
    if not lua_path:
        from sff.lua.choices import download_lua_direct
        from sff.lua.endpoints import POPUP_SHOWN
        endpoints = {"hubcap": LuaEndpoint.HUBCAP, "freelua": LuaEndpoint.FREELUA,
                     "ryuu": LuaEndpoint.RYUU, "depotbox": LuaEndpoint.DEPOTBOX}
        if source not in endpoints:
            source = "hubcap" if bridge._api_key else "freelua"
        progress("Downloading Lua")
        destination = Path.cwd() / "saved_lua"
        destination.mkdir(exist_ok=True)
        lua_path = download_lua_direct(dest=destination, app_id=app_id, source=endpoints[source],
                                       steam_path=bridge._steam_path, request_update=request_update,
                                       branch=branch, file_type=file_type)
        if lua_path == POPUP_SHOWN:
            return False
        if not lua_path:
            return "source_empty"
    lua_path = Path(lua_path)
    progress("Parsing Lua")
    if lua_path.suffix.lower() in (".zip", ".rar", ".7z"):
        from sff.zip import read_lua_from_zip
        contents = read_lua_from_zip(lua_path, decode=True, depotcache=bridge._steam_path / "depotcache")
    else:
        contents = lua_path.read_text(encoding="utf-8", errors="replace")
    if not contents or not re.search(r"^\s*addappid\s*\(\s*" + re.escape(app_id) + r"\s*[,)]", contents, re.MULTILINE):
        raise ValueError("Локальный Lua относится к другой игре.")
    parsed = parse_lua_contents(contents, lua_path)
    if not parsed or str(parsed.app_id) != app_id:
        raise ValueError("Локальный Lua относится к другой игре.")
    if lua_path.suffix.lower() != ".lua":
        destination = Path.cwd() / "saved_lua"
        destination.mkdir(exist_ok=True)
        lua_path = destination / (app_id + ".lua")
        lua_path.write_text(contents)
    from sff.game.download_queue import is_cancelled
    if is_cancelled(app_id):
        return False
    progress("Writing decryption keys")
    ConfigVDFWriter(bridge._steam_path).add_decryption_keys_to_config(parsed)
    progress("Installing Lua to Steam")
    if not install_lua_to_steam(bridge._steam_path, app_id, lua_path):
        raise ValueError("Не удалось сохранить Lua в Steam. Проверьте доступ к папке и повторите добавление.")
    for token_app, token in (parsed.token_overrides or {}).items():
        add_app_token(config, str(token_app), str(token))
    for depot_id, manifest in (parsed.manifest_overrides or {}).items():
        add_manifest_id(config, str(depot_id), str(manifest))
    write_native_keys(parsed)
    progress("Registering app ID")
    update_list("AdditionalApps", app_id, True, config)
    progress("Registering in library")
    bridge._installed_games_cache = None
    progress("Complete", 100)
    logger.info("Linux library entry %s registered; content installation is left to Steam", app_id)
    return True
