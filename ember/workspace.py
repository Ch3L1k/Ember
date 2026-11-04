# Ember — Copyright (C) 2026 Ember contributors.
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details (LICENSE).

import copy
import json
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class Workspace:
    def __init__(self, file):
        self.file = Path(file)
        self.data = {"revision": 0, "pins": [], "searches": [], "recent": [], "names": {}}
        try:
            value = json.loads(self.file.read_text(encoding="utf-8"))
            if not isinstance(value, dict) or not all(isinstance(value.get(key), list) for key in ("pins", "searches", "recent")):
                raise ValueError("Invalid workspace data")
            recent = [{**self.game(row), "success": row.get("success") is True, "message": str(row.get("message", ""))[:500], "time": min(4102444800, max(0, int(row.get("time", 0))))} for row in value["recent"][:12]]
            self.data.update({"revision": max(0, int(value.get("revision", 0))), "pins": [self.game(game) for game in value["pins"][:60]], "searches": [self.query(query) for query in value["searches"][:8]], "recent": recent})
            self.data["names"] = {game["app_id"]: game["name"] for game in self.data["pins"] + recent}
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError, KeyError):
            logger.warning("Could not load Ember workspace; retained the original file", exc_info=True)

    @staticmethod
    def game(value):
        if not isinstance(value, dict):
            raise ValueError("Invalid game")
        app_id, name = str(value.get("app_id", "")), str(value.get("name", ""))
        if len(app_id)>10 or not app_id.isascii() or not app_id.isdigit() or not 0 < int(app_id) <= 2147483647:
            raise ValueError("Invalid App ID")
        return {"app_id": app_id, "name": name.strip()[:200] or "Игра " + app_id}

    @staticmethod
    def query(value):
        if not isinstance(value, str):
            raise ValueError("Invalid search")
        return " ".join(value.split())[:100]

    def snapshot(self):
        return copy.deepcopy({key: self.data[key] for key in ("revision", "pins", "searches", "recent")})

    def commit(self, value):
        value["revision"] = self.data["revision"] + 1
        self.file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.file.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.file)
        self.data = value
        return self.snapshot()

    def update(self, request):
        if not isinstance(request, dict):
            raise ValueError("Invalid workspace request")
        data = copy.deepcopy(self.data)
        action = request.get("action")
        if action == "toggle_pin":
            game = self.game(request.get("game"))
            exists = any(item["app_id"] == game["app_id"] for item in data["pins"])
            if exists:
                data["pins"] = [item for item in data["pins"] if item["app_id"] != game["app_id"]]
            else:
                if len(data["pins"]) >= 60:
                    raise ValueError("В отложенном списке уже 60 игр. Уберите одну, чтобы добавить новую.")
                data["pins"].insert(0, game)
            data["names"][game["app_id"]] = game["name"]
        elif action == "remember_search":
            query = self.query(request.get("query"))
            if not query:
                return self.snapshot()
            data["searches"] = [query] + [old for old in data["searches"] if old.casefold() != query.casefold()][:7]
        elif action == "note_game":
            game = self.game(request.get("game"))
            data["names"][game["app_id"]] = game["name"]
        elif action == "clear_searches":
            data["searches"] = []
        elif action == "clear_recent":
            data["recent"] = []
        else:
            raise ValueError("Unknown workspace action")
        data["names"] = dict(list(data["names"].items())[-120:])
        return self.commit(data)

    def record(self, result):
        if result.get("task") != "download_fastest" or not result.get("app_id"):
            return None
        game = self.game({"app_id": result["app_id"], "name": self.data["names"].get(str(result["app_id"]), result.get("name", ""))})
        data = copy.deepcopy(self.data)
        row = {**game, "success": bool(result.get("success")), "message": str(result.get("message", ""))[:500], "time": int(time.time())}
        data["recent"] = [row] + [item for item in data["recent"] if item.get("app_id") != game["app_id"]][:11]
        return self.commit(data)
