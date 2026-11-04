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
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def millennium_installed(steam_path: Path) -> bool:
    return any((steam_path / location).is_file() for location in ("millennium/lib/millennium.dll", "lib/millennium.dll"))


def prepare_for_millennium(steam_path: Path, backup_dir: Path) -> Path | None:
    target = steam_path / "steam.cfg"
    if not target.exists():
        return None
    allowed = {"bootstrapperinhibitall", "bootstrapperforceselfupdate", "bootstrapperenableselfupdate"}
    for line in target.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", ";", "//")):
            continue
        key, separator, value = stripped.partition("=")
        if not separator or key.strip().lower() not in allowed or value.strip().lower() not in {"enable", "enabled", "disable", "disabled", "true", "false", "yes", "no", "0", "1"}:
            raise ValueError("Steam.cfg несовместим с Millennium и содержит дополнительные настройки. Файл сохранён без изменений.")
    backup_dir = backup_dir.resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"steam.cfg.{time.time_ns()}.bak"
    target.replace(backup)
    logger.info("Archived the Steam update blocker for Millennium: %s", backup)
    return backup


def _atomic_write(target: Path, payload: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(target)


def block_updates(steam_path: Path) -> None:
    if millennium_installed(steam_path):
        raise ValueError("Блокировка обновлений через Steam.cfg несовместима с Millennium.")
    target = steam_path / "steam.cfg"
    _atomic_write(target, "BootStrapperInhibitAll=Enable\n")


def unblock_updates(steam_path: Path) -> None:
    if millennium_installed(steam_path):
        prepare_for_millennium(steam_path, steam_path / "millennium/config/ember-backups")
        return
    target = steam_path / "steam.cfg"
    _atomic_write(target, "BootStrapperInhibitAll=False\n")
