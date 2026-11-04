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
import secrets
import sys
from pathlib import Path

from PyQt6.QtCore import QTimer, pyqtSlot
from PyQt6.QtWidgets import QApplication, QWidget

from ember import VERSION
from ember.config import DATA, ROOT, steam_path, write_runtime, lab_mode
from ember.rpc import Dispatcher, EventStream
from ember.server import LocalServer
from ember.window import EmberWindow, WindowActions

logger = logging.getLogger(__name__)


def main():
    logger.info("Initializing Ember runtime")
    os.environ["EMBER_DATA_DIR"] = str(DATA)
    from sff.core.structs import OSType, Settings
    from sff.core.storage.settings import get_setting, set_setting
    from sff.i18n import set_language
    from sff.gui.gui_prompts import install as install_gui_prompts
    from sff.gui.web_bridge import WebBridge
    from sff.ui.ui import UI
    from sff.network.steam_client import SteamInfoProvider
    from sff.downloads.download_manager import DownloadManager
    from steam.client import SteamClient
    from ember.cdp import SteamIntegration
    from ember.lab_policy import LabPolicy

    isolated = lab_mode()
    millennium = not isolated and os.environ.get("EMBER_INTEGRATION") == "millennium"
    embedded = not isolated and os.name != "nt" and not millennium
    path = steam_path()
    policy = LabPolicy(os.environ["EMBER_LAB_ROOT"], path) if isolated else None
    from ember.workspace import Workspace
    workspace = Workspace(DATA / "workspace.json")
    from ember.library import Library
    library = Library(path, DATA)

    class EmberBridge(WebBridge):
        @pyqtSlot(str, result=str)
        def get_webui_translations(self, language):
            from ember.localization import web_translations
            return json.dumps(web_translations(ROOT, language))

        @pyqtSlot(str, result=str)
        def ember_set_language(self, language):
            if language not in ('ru', 'en'):
                raise ValueError('Unsupported interface language')
            set_setting(Settings.LANGUAGE, language)
            set_language(language)
            runtime = json.loads((DATA / 'runtime.json').read_text(encoding='utf-8'))
            runtime['language'] = language
            write_runtime(runtime)
            server.language = language
            self.task_finished.emit(json.dumps({'task': 'ember_language', 'language': language}))
            return language

        @pyqtSlot(result=str)
        def ember_get_workspace(self):
            return json.dumps(workspace.snapshot())

        @pyqtSlot(str, result=str)
        def ember_update_workspace(self, payload):
            value = workspace.update(json.loads(payload))
            self.task_finished.emit(json.dumps({"task": "ember_workspace", "workspace": value}))
            return json.dumps(value)

        @pyqtSlot(str)
        def _ember_record_task(self, payload):
            try:
                result = json.loads(payload)
                if result.get("task") == "download_fastest":
                    getattr(self, "_ember_additions_active", set()).discard(str(result.get("app_id")))
                value = workspace.record(result)
                if value:
                    self.task_finished.emit(json.dumps({"task": "ember_workspace", "workspace": value}))
            except Exception:
                logger.warning("Could not save Ember activity", exc_info=True)

        @pyqtSlot(str)
        def _ember_track_addition(self, payload):
            try:
                app_id = str(json.loads(payload).get("app_id", ""))
                if app_id.isascii() and app_id.isdigit():
                    if not hasattr(self, "_ember_additions_active"):
                        self._ember_additions_active = set()
                    self._ember_additions_active.add(app_id)
            except (ValueError, TypeError):
                logger.debug("Ignored invalid addition progress", exc_info=True)

        def _ember_library_work(self, app_id="", action="refresh"):
            if getattr(self, "_ember_library_busy", False):
                raise ValueError("Дождитесь завершения операции с библиотекой")
            if action != "refresh":
                library.app_id(app_id)
            if action == "remove" and app_id in getattr(self, "_ember_additions_active", set()):
                raise ValueError("Дождитесь завершения добавления этой игры")
            installed = json.loads(self.get_installed_games())
            names = dict(workspace.data["names"])
            self._ember_library_busy = True
            if isolated:
                names.update({str(game['app_id']): game['name'] for game in json.loads((policy.root/'catalog.json').read_text(encoding='utf-8'))})
            def work():
                try:
                    if not isolated:
                        from sff import game_list_fallback as fallback
                        fallback.ensure_loaded_cached()
                        for key in library.registrations():
                            names.setdefault(key, fallback._games_cache.get(key, {}).get('name') or fallback._name_cache.get(key) or 'App ' + key)
                    games = library.snapshot(installed, names)
                    game = next((item for item in games if item['app_id'] == app_id), None)
                    result = {"success": True}
                    if action != "refresh" and not game:
                        raise ValueError("Игра не найдена. Обновите библиотеку.")
                    if action == "remove":
                        library.remove(app_id, game['name'])
                        result['message'] = "Регистрация Ember удалена. Файлы игры и сохранения сохранены. Если игра остаётся в Steam, перезапустите Steam."
                    elif action == "restore":
                        library.restore(app_id)
                        result['message'] = "Регистрация восстановлена. Если игра не появилась в Steam, перезапустите Steam."
                    elif action in ('download', 'play', 'store', 'folder', 'steam'):
                        if action in ('play', 'folder') and not game.get('installed'):
                            raise ValueError("Сначала установите игру через Steam")
                        if action == 'folder':
                            folder = Path(game['path']).resolve()
                            if isolated: policy.checked_path(folder)
                            if not folder.is_dir(): raise ValueError("Папка игры не найдена")
                            result['url'] = folder.as_uri()
                        else:
                            result['url'] = {'download': 'steam://install/', 'play': 'steam://run/', 'steam': 'steam://nav/games/details/', 'store': 'steam://store/'}[action] + app_id
                        result['message'] = "Команда передана Steam." if action != 'folder' else "Папка игры открыта."
                    result['games'] = library.snapshot(installed, names)
                    return result
                except Exception as error:
                    logger.warning("Library %s failed for app %s", action, app_id, exc_info=True)
                    return {"success": False, "message": str(error)}
            def done(result):
                self._ember_library_busy = False
                result = result or {"success": False, "message": "Не удалось прочитать библиотеку"}
                url = result.pop('url', None)
                if url:
                    if isolated:
                        result['simulated'] = True
                        result['message'] = "Тестовая среда: запуск Steam и открытие папок отключены."
                    else:
                        from PyQt6.QtCore import QUrl
                        from PyQt6.QtGui import QDesktopServices
                        if not QDesktopServices.openUrl(QUrl(url)):
                            result.update(success=False, message="Не удалось передать команду Steam")
                self.task_finished.emit(json.dumps({"task": "ember_library", "action": action, "app_id": app_id, **result}))
            self._run_async(work, on_done=done)

        @pyqtSlot()
        def ember_library_refresh(self):
            self._ember_library_work()

        @pyqtSlot(str, str)
        def ember_library_action(self, app_id, action):
            if action not in ('remove', 'restore', 'download', 'play', 'store', 'folder', 'steam'):
                raise ValueError("Неизвестное действие библиотеки")
            self._ember_library_work(app_id, action)

        @pyqtSlot(str, str)
        def ember_tool_action(self, app_id, action):
            if isolated:
                raise PermissionError("Изменения игр отключены в лаборатории")
            if action not in ("inspect", "dlc_install", "dlc_remove", "diagnose", "repair_launch") or not app_id.isdigit():
                raise ValueError("Некорректное действие инструмента")
            active = getattr(self, "_ember_tools_active", set())
            self._ember_tools_active = active
            if app_id in active:
                raise ValueError("Дождитесь завершения предыдущей операции с этой игрой")
            active.add(app_id)
            def work():
                from ember.tools import run_tool
                try:
                    return {"success": True, **run_tool(self, app_id, action)}
                except Exception as error:
                    logger.warning("Ember tool %s failed for %s: %s", action, app_id, error, exc_info=True)
                    return {"success": False, "message": str(error)}
            def done(result):
                active.discard(app_id)
                result = result or {"success": False, "message": "Не удалось получить результат инструмента"}
                self.task_finished.emit(json.dumps({"task": "ember_tool", "app_id": app_id, "action": action, **result}))
            self._run_async(work, on_done=done)

        @pyqtSlot(str)
        def ember_lab_add_game(self, payload):
            if not isolated:
                raise PermissionError("Available only in Ember Lab")
            data = json.loads(payload)
            fixture_ids = ("900000001", "900000002", "900000003")
            if data.get('name') == 'search_results':
                result = data.get('data', {})
                if not str(result.get('request_id', '')).isdigit() or any(str(game.get('app_id')) not in fixture_ids for game in result.get('games', [])):
                    raise ValueError('Invalid fixture search result')
            elif data.get("name") not in ("download_progress", "task_finished") or str(data.get("data", {}).get("app_id")) not in fixture_ids:
                raise ValueError("Invalid fixture event")
            getattr(self, data["name"]).emit(json.dumps(data["data"]))

        @pyqtSlot()
        def ember_refresh_games(self):
            self._prefetch_installed_games()

        def _prefetch_installed_games(self):
            if isolated or getattr(self, "_ember_games_scanning", False):
                return
            self._ember_games_scanning = True
            def work():
                return self._scan_installed_games()
            def done(payload):
                import time
                self._ember_games_scanning = False
                if payload:
                    self._installed_games_cache = (time.monotonic(), payload)
                    self.task_finished.emit(json.dumps({"task": "ember_games_loaded", "games": json.loads(payload)}))
            self._run_async(work, on_done=done)

        @pyqtSlot()
        def ember_open_window(self):
            if isolated:
                raise PermissionError("Available only in the desktop client")
            if millennium:
                import time
                (DATA / "open-request.txt").write_text(str(time.time_ns()), encoding="utf-8")
            else:
                window_actions.open_requested.emit()

        @pyqtSlot()
        def ember_quit(self):
            QTimer.singleShot(200, QApplication.instance().quit)

        def _scan_installed_games(self):
            if not isolated:
                return super()._scan_installed_games()
            import vdf
            games = []
            for manifest in (path / "steamapps").glob("appmanifest_*.acf"):
                state = vdf.loads(manifest.read_text(encoding="utf-8"))["AppState"]
                game_path = policy.checked_path(path / "steamapps/common" / state["installdir"])
                if game_path.is_dir():
                    games.append({"app_id": int(state["appid"]), "name": state["name"], "path": str(game_path), "installed": True, "steamidra_managed": False, "steamidra_source": "", "image_url": "/ember/mark.svg"})
            return json.dumps(games)

        def _get_store_client(self):
            return None if isolated else super()._get_store_client()

        def _check_provider_keys_startup(self):
            if not isolated:
                return super()._check_provider_keys_startup()

        def _maybe_auto_contribute_provider(self):
            logger.debug("Automatic provider submission is disabled in Ember")

        def _maybe_auto_refresh_provider_cache(self):
            if not isolated:
                return super()._maybe_auto_refresh_provider_cache()

        def _advance_download_queue(self):
            if not isolated:
                return super()._advance_download_queue()

        def _process_acf_queue(self):
            if not isolated:
                return super()._process_acf_queue()

        def _run_flat_file_repair(self):
            if not isolated:
                return super()._run_flat_file_repair()

        def _run_async(self, func, *args, **kwargs):
            if func.__name__ == "_prefetch_crack_buildids" or (isolated and func.__name__ == "_warm_steam_session_worker"):
                logger.debug("Ember skipped unused network prefetch: %s", func.__name__)
                return
            return super()._run_async(func, *args, **kwargs)

        def _ensure_steam_dirs_and_update_lock(self):
            logger.debug("Ember initialization leaves Steam configuration unchanged")

        @pyqtSlot(result=str)
        def get_app_version(self):
            return VERSION

        @pyqtSlot(str, result=str)
        def app_update_check(self, _arg=""):
            return json.dumps({"ok": True, "update_available": False, "current": VERSION, "latest": VERSION, "source": "local-development"})

        @pyqtSlot(result=str)
        def get_installed_games(self):
            if not isolated:
                cached = getattr(self, "_installed_games_cache", None)
                if cached:
                    return cached[1]
                self._prefetch_installed_games()
                return "[]"
            return super().get_installed_games()

        @pyqtSlot()
        def load_library(self):
            if not isolated:
                return super().load_library()
            self.task_finished.emit(json.dumps({"task": "library_loaded", "success": True, "games": json.loads(self.get_installed_games())}))

        @pyqtSlot()
        def refresh_library(self):
            self._installed_games_cache = None
            return self.load_library()

        @pyqtSlot(str)
        def fetch_library_images(self, app_ids_json):
            if not isolated:
                return super().fetch_library_images(app_ids_json)
            self.task_finished.emit(json.dumps({"task": "library_images", "success": True, "images": {str(app): "/ember/mark.svg" for app in json.loads(app_ids_json)}}))

        @pyqtSlot(str, result=str)
        def get_cover_urls(self, app_ids_json):
            if not isolated:
                return super().get_cover_urls(app_ids_json)
            return json.dumps({str(app): "/ember/mark.svg" for app in json.loads(app_ids_json)})

        @pyqtSlot(str, result=str)
        def lumacore_check_update(self, force=""):
            if not isolated:
                return super().lumacore_check_update(force)
            return json.dumps({"installed": "", "latest": "", "update_available": False, "source": "isolated-lab"})

        @pyqtSlot(result=str)
        def steam_is_running(self):
            if isolated:
                return "false"
            return super().steam_is_running()

        @pyqtSlot(str, int, int, str, str, str)
        def search_games(self, query, offset, per_page, sort_by="updated", tag="", request_id=""):
            if not isolated:
                if query.strip():
                    from ember.catalog_search import search
                    return search(self, query, offset, per_page, sort_by, tag, request_id)
                self._ember_catalog_current = None
                self._ember_catalog_local_pending = None
                self._ember_catalog_remote_pending = None
                return super().search_games(query, offset, per_page, sort_by, tag, request_id)
            catalog = json.loads((policy.root / "catalog.json").read_text(encoding="utf-8"))
            games = [game for game in catalog if query.casefold() in game["name"].casefold() or query == game["app_id"]]
            self.search_results.emit(json.dumps({"games": games[offset:offset + per_page], "total": len(games), "offset": offset, "per_page": per_page, "query": query, "request_id": request_id, "has_more": offset + per_page < len(games)}))

        @pyqtSlot(result=str)
        def ember_lab_state(self):
            if not isolated:
                return json.dumps({"enabled": False})
            return json.dumps({"enabled": True, "root": str(policy.root), "steam": str(path), "data": str(DATA), "real_steam_access": False})

        @pyqtSlot(result=str)
        def ember_lab_backup(self):
            if not isolated:
                raise RuntimeError("Available only in Ember Lab")
            import shutil
            save = policy.checked_path(policy.root / "saves/demo.json")
            backup = policy.checked_path(policy.root / "backups/demo.json")
            backup.parent.mkdir(exist_ok=True)
            shutil.copy2(save, backup)
            return json.dumps({"ok": True, "file": str(backup)})

        @pyqtSlot(result=str)
        def ember_lab_restore(self):
            if not isolated:
                raise RuntimeError("Available only in Ember Lab")
            import shutil
            shutil.copy2(policy.checked_path(policy.root / "backups/demo.json"), policy.checked_path(policy.root / "saves/demo.json"))
            return json.dumps({"ok": True})

    app = QApplication(sys.argv)
    logger.info("Ember application initialized")
    app.setApplicationName("Ember")
    app.setApplicationDisplayName("Ember")
    app.setDesktopFileName("ember")
    app.setQuitOnLastWindowClosed(False)
    install_gui_prompts()
    lang = get_setting(Settings.LANGUAGE)
    lang = lang if lang in ('ru', 'en') else 'ru'
    set_setting(Settings.LANGUAGE, lang)
    set_language(str(lang))
    set_setting(Settings.STEAM_PATH, str(path))
    parent = QWidget()
    parent.setWindowTitle("Ember")
    ui = UI(SteamInfoProvider(SteamClient()), path, OSType.WINDOWS if os.name == "nt" else OSType.LINUX)
    ui.download_manager = DownloadManager()
    bridge = EmberBridge(ui, path, parent)
    bridge.task_finished.connect(bridge._ember_record_task)
    bridge.download_progress.connect(bridge._ember_track_addition)
    logger.info("Ember bridge initialized")
    stream = EventStream()
    dispatcher = Dispatcher(bridge, stream, policy=policy)
    token = secrets.token_urlsafe(32)
    server = LocalServer(dispatcher, stream, token, mode="lab" if isolated else "desktop")
    server.language = lang
    server.start()
    native_window = EmberWindow(server.origin, token, state_path=DATA / "window-state.bin") if not isolated and not millennium and not embedded else None
    if native_window and os.environ.get("EMBER_OPEN_STANDALONE") == "1":
        QTimer.singleShot(0, native_window.open_panel)
    logger.info("Ember window initialized")
    window_actions = WindowActions()
    if native_window:
        window_actions.open_requested.connect(native_window.open_panel)
    ports = tuple(int(value) for value in os.environ.get("EMBER_CDP_PORTS", "").split(",") if value)
    if millennium:
        from ember.millennium import MillenniumIntegration
        integration = MillenniumIntegration(server, DATA)
    else:
        integration = SteamIntegration(server, ports=ports, allowed_origin=server.origin if isolated else None, open_on_connect=os.environ.get("EMBER_OPEN_ON_CONNECT") == "1", on_open_panel=window_actions.open_requested.emit if native_window else None)
        if embedded:
            def open_embedded():
                from PyQt6.QtCore import QUrl
                from PyQt6.QtGui import QDesktopServices
                QDesktopServices.openUrl(QUrl("steam://open/games"))
                QTimer.singleShot(300, integration.show_embedded)
            window_actions.open_requested.connect(open_embedded)
            integration.on_before_open = window_actions.open_requested.emit
    integration.start()
    write_runtime({"pid": os.getpid(), "origin": server.origin, "token": token, "version": VERSION, "mode": "lab" if isolated else "desktop", "integration": "millennium" if millennium else "cdp", "language": lang, "window_handle": int(native_window.winId()) if native_window else None})
    logger.info("Ember backend ready with %d methods", len(dispatcher.methods))

    class ForwardLogs(logging.Handler):
        def emit(self, record):
            if record.name.startswith("ember.server"):
                return
            if record.levelno >= logging.INFO:
                stream.publish("log_message", [self.format(record)])

    forward = ForwardLogs()
    forward.setFormatter(logging.Formatter("[%(levelname)s] %(name)s — %(message)s"))
    logging.getLogger().addHandler(forward)

    def shutdown():
        integration.stop()
        if native_window:
            native_window.shutdown()
        server.shutdown()
        ui.kill_midi_player()
        runtime = DATA / "runtime.json"
        if runtime.exists():
            payload = json.loads(runtime.read_text(encoding="utf-8"))
            if payload.get("pid") == os.getpid():
                runtime.unlink()

    app.aboutToQuit.connect(shutdown)
    app._ember = (parent, ui, bridge, dispatcher, server, integration, stream, native_window, window_actions)
    return app.exec()
