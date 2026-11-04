# SteaMidra - Steam game setup and manifest tool (SFF)
# Copyright (c) 2025-2026 Midrag (https://github.com/Midrags)
#
# This file is part of SteaMidra.
#
# SteaMidra is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SteaMidra is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SteaMidra.  If not, see <https://www.gnu.org/licenses/>.

"""Build a nested folder/file tree from decoded manifest mappings.

Used by the Advanced depot picker's per-depot file explorer modal.
"""

_DIR_FLAGS = 0x40


def _norm(filename: str):
    if not filename:
        return None
    cleaned = str(filename).replace("\\", "/")
    parts = []
    for part in cleaned.split("/"):
        part = part.strip()
        if not part or part == ".":
            continue
        if part == "..":
            return None
        parts.append(part)
    return parts or None


def build_file_tree(mappings: list) -> dict:
    """mappings: decode_manifest() output rows ({filename,size,flags}).
    Returns {"name": "", "size": n, "children": [...}] with folders first,
    each sorted case-insensitively. Folder size is the sum of its files."""
    root = {"name": "", "dir": True, "size": 0, "children": {}}
    for m in mappings or []:
        parts = _norm(m.get("filename", ""))
        if not parts:
            continue
        is_dir = bool(m.get("flags", 0) & _DIR_FLAGS)
        if is_dir and not m.get("size"):
            # A directory record in the manifest: ensure the node exists,
            # its size comes from the files under it.
            node = root
            for part in parts:
                node = node["children"].setdefault(
                    part.lower() + "/" + part,
                    {"name": part, "dir": True, "size": 0, "children": {}},
                )
            continue
        node = root
        for part in parts[:-1] if not is_dir else parts:
            key = part.lower() + "/" + part
            node = node["children"].setdefault(
                key, {"name": part, "dir": True, "size": 0, "children": {}})
        if is_dir:
            continue
        fname = parts[-1]
        size = int(m.get("size", 0) or 0)
        node["children"][fname.lower() + "/" + fname] = {
            "name": fname, "dir": False, "size": size, "path": "/".join(parts)}
        root["size"] += size

    def _finalize(node):
        total = 0
        kids = []
        for child in node["children"].values():
            if child["dir"]:
                _finalize(child)
                total += child["size"]
            else:
                total += child["size"]
            kids.append(child)
        node["size"] = max(node["size"], total) if node["dir"] else node["size"]
        kids.sort(key=lambda c: (not c["dir"], c["name"].lower()))
        node["children"] = kids

    def _strip(node):
        out = {"name": node["name"], "size": node["size"]}
        if node["dir"]:
            out["children"] = [_strip(c) for c in node["children"]]
        else:
            out["path"] = node["path"]
        return out

    _finalize(root)
    return _strip(root)


if __name__ == "__main__":
    tree = build_file_tree([
        {"filename": "Game\\Data\\alpha.txt", "size": 10, "flags": 0},
        {"filename": "Game/Data/beta.bin", "size": 20, "flags": 0},
        {"filename": "Game\\Launcher.exe", "size": 5, "flags": 0},
        {"filename": "../escape.txt", "size": 1, "flags": 0},
        {"filename": "Game\\Empty", "size": 0, "flags": 0x40},
    ])
    assert tree["size"] == 35
    assert [c["name"] for c in tree["children"]] == ["Game"]
    game = tree["children"][0]
    assert game["size"] == 35
    assert [c["name"] for c in game["children"]] == ["Data", "Empty", "Launcher.exe"]
    data = game["children"][0]
    assert [c["name"] for c in data["children"]] == ["alpha.txt", "beta.bin"]
    assert data["children"][0]["path"] == "Game/Data/alpha.txt"
    assert all(c["name"] != "escape.txt" for c in tree["children"])
    print("filetree self-check OK")
