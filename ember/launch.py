# Ember — Copyright (C) 2026 Ember contributors.
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import sys
from pathlib import Path


def install_root():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def launch_command(*arguments):
    if getattr(sys, "frozen", False):
        return [sys.executable, *arguments]
    executable = Path(sys.executable)
    if os.name == "nt":
        windowed = executable.with_name("pythonw.exe")
        if windowed.is_file():
            executable = windowed
    return [str(executable), str(install_root() / "EmberRuntime.py"), *arguments]
