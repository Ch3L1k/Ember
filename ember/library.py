# Ember — Copyright (C) 2026 Ember contributors.
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details (LICENSE).

import hashlib
import json
import logging
import os
import re
import shutil
import threading
import tempfile
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class Library:
    def __init__(self, steam, data):
        self.steam = Path(steam).resolve()
        self.plugins = self.steam / "config/stplug-in"
        self.backups = Path(data).resolve() / "library-removals"
        self.lock = threading.RLock()

    @staticmethod
    def app_id(value):
        if not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]{0,9}", value) or int(value) > 4294967295:
            raise ValueError("Некорректный App ID")
        return value

    def safe_plugin(self, relative):
        path = self.plugins / relative
        if not path.resolve().is_relative_to(self.plugins.resolve()) or not path.resolve().is_relative_to(self.steam) or path.is_symlink():
            raise ValueError("Файл регистрации находится за пределами папки Steam")
        return path

    def registrations(self):
        result = {}
        for file in list(self.plugins.glob("*.lua")) + list(self.plugins.glob("*/*.lua")):
            try:
                relative = file.relative_to(self.plugins)
                self.safe_plugin(relative)
                if not file.is_file() or (file.parent == self.plugins and file.name.lower() in ("00_letupdate_override.lua", "letupdate_override.lua")):
                    continue
                parent_id = file.parent.name if file.parent != self.plugins else ""
                candidate = parent_id if parent_id.isascii() and parent_id.isdigit() else file.stem
                if not candidate.isascii() or not candidate.isdigit():
                    with file.open(encoding="utf-8", errors="replace") as handle:
                        text = handle.read(1024*1024)
                    match = re.search(r"addappid\s*\(\s*([1-9][0-9]*)", text, re.I)
                    candidate = match[1] if match else ""
                app_id = self.app_id(candidate)
                result.setdefault(app_id, []).append(file)
            except (OSError, ValueError):
                logger.debug("Skipped unsupported library registration: %s", file, exc_info=True)
        return result

    def removed(self):
        records = {}
        for file in sorted(self.backups.glob("*/record.json"), reverse=True):
            try:
                value = json.loads(file.read_text(encoding="utf-8"))
                app_id = self.app_id(value["app_id"])
                if value.get("state") in ("removed", "removing") and app_id not in records:
                    records[app_id] = (file, value)
            except (OSError, ValueError, KeyError, TypeError):
                logger.warning("Could not read a library removal record", exc_info=True)
        return records

    def snapshot(self, installed, names=None):
        names = names or {}
        with self.lock:
            registrations, removed = self.registrations(), self.removed()
            games = {str(game["app_id"]): {**game, "app_id": str(game["app_id"])} for game in installed}
            for app_id in registrations.keys() | removed.keys():
                record = removed.get(app_id, (None, {}))[1]
                games.setdefault(app_id, {"app_id": app_id, "name": names.get(app_id) or record.get("name") or "App " + app_id, "installed": False, "path": ""})
            for app_id, game in games.items():
                game.update(managed=app_id in registrations, removed=app_id in removed and app_id not in registrations,
                            can_remove=app_id in registrations, can_restore=app_id in removed and app_id not in registrations)
            return sorted(games.values(), key=lambda game: game["name"].casefold())

    @staticmethod
    def write_record(file, value):
        temporary = file.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        temporary.replace(file)

    @staticmethod
    def digest(file):
        return hashlib.sha256(file.read_bytes()).hexdigest()

    @staticmethod
    def _rollback(actions):
        failures = []
        for action in reversed(actions):
            try:
                action()
            except Exception as error:
                failures.append(str(error))
                logger.exception("Library transaction rollback failed")
        return failures

    @staticmethod
    def _change_registration(record, app_id, enabled, undo):
        if record.get("sls_registered"):
            from ember.linux_tools import update_list
            previous = update_list("AdditionalApps", app_id, enabled)
            undo.append(lambda previous=previous: update_list("AdditionalApps", app_id, previous))
        if record.get("native_entries"):
            from ember.linux_registration import native_entries, restore_native_entries
            previous = native_entries(app_id)
            changed = {key: value for key, value in record["native_entries"].items()
                       if (key not in previous if enabled else key in previous)}
            restore_native_entries(record["native_entries"], enabled)
            undo.append(lambda: restore_native_entries(changed, not enabled))

    def remove(self, app_id, name):
        app_id = self.app_id(app_id)
        with self.lock:
            files = self.registrations().get(app_id, [])
            if not files:
                raise ValueError("У игры нет регистрации Ember для удаления")
            self.backups.mkdir(parents=True, exist_ok=True)
            folder = Path(tempfile.mkdtemp(prefix=f"{time.time_ns()}-{app_id}-", dir=self.backups))
            entries = []
            for source in files:
                relative = source.relative_to(self.plugins)
                destination = folder / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
                digest = self.digest(source)
                if self.digest(destination) != digest:
                    raise OSError("Не удалось проверить резервную копию регистрации")
                entries.append({"path": relative.as_posix(), "sha256": digest})
            record = {"app_id": app_id, "name": str(name)[:200], "state": "removing", "files": entries}
            if os.name != "nt" and os.environ.get("EMBER_MODE") == "desktop":
                from ember.linux_tools import read_config
                _, settings = read_config()
                record["sls_registered"] = app_id in {str(item) for item in settings.get("AdditionalApps") or []}
                from ember.linux_registration import native_entries
                record["native_entries"] = native_entries(app_id)
            record_file = folder / "record.json"
            self.write_record(record_file, record)
            deleted = []
            undo = []
            try:
                for entry in entries:
                    source = self.safe_plugin(entry["path"])
                    if self.digest(source) != entry["sha256"]:
                        raise OSError("Регистрация изменилась во время удаления. Повторите действие.")
                    source.unlink()
                    deleted.append(entry)
                record["state"] = "removed"
                self._change_registration(record, app_id, False, undo)
                self.write_record(record_file, record)
            except Exception:
                for entry in deleted:
                    def restore_file(entry=entry):
                        destination = self.safe_plugin(entry["path"])
                        if not destination.exists():
                            shutil.copy2(folder / entry["path"], destination)
                    undo.append(restore_file)
                failures = self._rollback(undo)
                record["state"] = "removing" if failures else "failed"
                record["rollback_errors"] = failures
                try:
                    self.write_record(record_file, record)
                except Exception:
                    logger.exception("Could not update recovery record: %s", record_file)
                logger.warning("Library operation rolled back for app %s; rollback errors: %s", app_id, failures, exc_info=True)
                raise
            logger.info("Archived library registration for app %s (%s files)", app_id, len(entries))

    def restore(self, app_id):
        app_id = self.app_id(app_id)
        with self.lock:
            found = self.removed().get(app_id)
            if not found:
                raise ValueError("Резервная копия регистрации не найдена")
            record_file, record = found
            entries = record["files"]
            for entry in entries:
                source = record_file.parent / entry["path"]
                if not source.resolve().is_relative_to(record_file.parent.resolve()) or source.is_symlink() or self.digest(source) != entry["sha256"]:
                    raise ValueError("Резервная копия регистрации повреждена")
                if self.safe_plugin(entry["path"]).exists():
                    raise ValueError("Регистрация уже существует. Существующие файлы не заменены.")
            created = []
            undo = []
            try:
                for entry in entries:
                    destination = self.safe_plugin(entry["path"])
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with destination.open("xb") as output:
                        output.write((record_file.parent / entry["path"]).read_bytes())
                    created.append(entry)
                record["state"] = "restored"
                self._change_registration(record, app_id, True, undo)
                self.write_record(record_file, record)
            except Exception:
                for entry in created:
                    def remove_file(entry=entry):
                        destination = self.safe_plugin(entry["path"])
                        if destination.exists() and self.digest(destination) == entry["sha256"]:
                            destination.unlink()
                    undo.append(remove_file)
                failures = self._rollback(undo)
                record["state"] = "removed"
                record["rollback_errors"] = failures
                try:
                    self.write_record(record_file, record)
                except Exception:
                    logger.exception("Could not update recovery record: %s", record_file)
                logger.warning("Library operation rolled back for app %s; rollback errors: %s", app_id, failures, exc_info=True)
                raise
            logger.info("Restored library registration for app %s", app_id)
