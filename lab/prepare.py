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
from pathlib import Path

import msgpack
import vdf


def prepare(root):
    root = Path(root).resolve()
    if root.exists() and any(root.iterdir()) and not (root / ".ember-lab").is_file():
        raise ValueError("The selected directory is not an Ember Lab")
    root.mkdir(parents=True, exist_ok=True)
    (root / ".ember-lab").write_text("Ember Lab fixture version 1\n", encoding="utf-8")
    steam = root / "Steam"
    for directory in ("config/stplug-in", "steamapps/common", "depotcache", "userdata", "lumacore"):
        (steam / directory).mkdir(parents=True, exist_ok=True)
    (steam / "config/libraryfolders.vdf").write_text(vdf.dumps({"libraryfolders": {"0": {"path": str(steam), "apps": {"900000001": "2048"}}}}), encoding="utf-8")
    (steam / "config/loginusers.vdf").write_text(vdf.dumps({"users": {}}), encoding="utf-8")
    (steam / "steam.cfg").write_text("BootStrapperInhibitAll=False\n", encoding="utf-8")
    game = steam / "steamapps/common/Ember Demo"
    game.mkdir(exist_ok=True)
    (game / "lab-data.txt").write_text("Ember Lab fixture. No game executable or account data.\n", encoding="utf-8")
    (steam / "steamapps/appmanifest_900000001.acf").write_text(vdf.dumps({"AppState": {"appid": "900000001", "name": "Ember Demo", "installdir": "Ember Demo", "StateFlags": "4", "SizeOnDisk": "2048", "buildid": "1", "LastUpdated": "1700000000"}}), encoding="utf-8")
    catalog = [{"app_id": "900000001", "name": "Ember Demo", "image_url": "/ember/mark.svg", "platforms": {"windows": True}}, {"app_id": "900000002", "name": "Ember Puzzle", "image_url": "/ember/mark.svg", "platforms": {"windows": True}}, {"app_id": "900000003", "name": "Ember Racing", "image_url": "/ember/mark.svg", "platforms": {"windows": True}}]
    (root / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    data = root / "Data"
    data.mkdir(exist_ok=True)
    for app_id in ("900000001", "900000002"):
        (steam / "config/stplug-in" / (app_id + ".lua")).write_text("-- Ember Lab fixture\naddappid(" + app_id + ")\n", encoding="utf-8")
    from sff.core.structs import Settings
    settings = {Settings.STEAM_PATH.key_name: str(steam), Settings.LANGUAGE.key_name: "ru", Settings.PLAY_MUSIC.key_name: False, Settings.PROVIDER_CONTRIBUTE_KEYS.key_name: False}
    target = data / "settings.bin"
    if not target.exists():
        target.write_bytes(msgpack.packb(settings))
    (root / "saves").mkdir(exist_ok=True)
    save = root / "saves/demo.json"
    if not save.exists():
        save.write_text(json.dumps({"level": 7, "coins": 42}), encoding="utf-8")
    return {"root": str(root), "steam": str(steam), "data": str(data)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    arguments = parser.parse_args()
    print(json.dumps(prepare(arguments.root)))
