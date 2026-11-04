# Ember — Copyright (C) 2026 Ember contributors.
# SPDX-License-Identifier: GPL-3.0-or-later

import argparse
import datetime
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description="Install Ember launchers for the current Linux user")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    home = Path.home()
    interpreter = ROOT / ".venv/bin/python"
    if not interpreter.is_file():
        raise SystemExit("Create the project .venv and install requirements-linux.txt first")
    launcher = home / ".local/bin/ember"
    desktop = home / ".local/share/applications/ember.desktop"
    icon = home / ".local/share/icons/hicolor/256x256/apps/ember.png"
    if not args.apply:
        for path in (launcher, desktop, icon):
            print(path)
        print("Use --apply to install these launchers.")
        return
    import shlex
    backup = home / ".local/state/ember-linux-backups" / datetime.datetime.now().strftime("launchers-%Y%m%d-%H%M%S")
    backup.mkdir(parents=True, mode=0o700)
    for path in (launcher, desktop, icon):
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            shutil.copy2(path, backup / path.name)
    launcher.write_text("#!/bin/sh\nexec " + shlex.quote(str(interpreter)) + " " +
                        shlex.quote(str(ROOT / "EmberRuntime.py")) + ' "$@"\n')
    launcher.chmod(0o755)
    desktop.write_text("[Desktop Entry]\nType=Application\nName=Ember\nComment=Steam library and game tools\n"
                       'Exec="' + str(launcher).replace('"', '\\"') + '"\nIcon=ember\nTerminal=false\n'
                       "Categories=Game;Utility;\nStartupWMClass=Ember\nStartupNotify=true\n")
    shutil.copy2(ROOT / "ember/web/Ember.png", icon)
    print("Installed Ember. Backup:", backup)


if __name__ == "__main__":
    main()
