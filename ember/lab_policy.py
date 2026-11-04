# Ember — Copyright (C) 2026 Ember contributors.
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details (LICENSE).

import json
from pathlib import Path

READ_ONLY = frozenset({
    "signal_ready", "get_platform", "is_steamos", "get_app_version", "app_update_check",
    "get_webui_translations", "get_setting", "get_all_settings", "get_steam_libraries",
    "get_storage_paths", "get_disk_usage", "get_stored_api_key", "get_gse_identity",
    "get_avatar_base64", "get_games_file_info", "get_game_list", "get_applist_games",
    "get_fix_game_list", "get_installed_games", "load_library", "refresh_library",
    "get_recent_lua_files", "get_custom_save_paths", "get_game_update_state",
    "get_game_update_override", "get_game_update_check", "get_launch_option_status",
    "download_queue_get_state", "get_download_queue_state", "get_download_history",
    "download_history_list", "get_active_downloads", "get_cover_urls", "get_library_images",
    "get_downloads", "lumacore_check_update", "steam_is_running", "steam_updates_get_state",
    "get_launch_options", "let_updates_list_games", "get_provider_cache_status",
    "list_profiles", "search_games", "search_games_file", "get_game_branches", "check_lua_folder_migration",
    "ember_lab_state", "ember_lab_backup", "ember_lab_restore", "ember_lab_add_game", "ember_refresh_games", "ember_get_workspace", "ember_update_workspace", "ember_set_language",
    "ember_library_refresh", "ember_library_action",
})


class LabPolicy:
    def __init__(self, root, steam):
        self.root = Path(root).resolve()
        self.steam = Path(steam).resolve()
        if not self.steam.is_relative_to(self.root) or not (self.root / ".ember-lab").is_file():
            raise RuntimeError("Invalid Ember Lab root")
        libraries = self.steam / "config/libraryfolders.vdf"
        if libraries.exists():
            import vdf
            data = vdf.loads(libraries.read_text(encoding="utf-8"))
            for value in data.get("libraryfolders", {}).values():
                if isinstance(value, dict) and "path" in value:
                    if not Path(value["path"]).resolve().is_relative_to(self.root):
                        raise RuntimeError("A lab library points outside the isolated root")

    def check(self, method, args):
        if method not in READ_ONLY:
            raise PermissionError("Ember Lab: это действие доступно только в отдельной виртуальной машине. Основной Steam не затрагивается.")

    def checked_path(self, path):
        resolved = Path(path).resolve()
        if not resolved.is_relative_to(self.root):
            raise PermissionError("Path is outside Ember Lab")
        return resolved
