# Ember — Copyright (C) 2026 Ember contributors.
# SPDX-License-Identifier: GPL-3.0-or-later

import faulthandler
import logging
import multiprocessing
import os
import sys
from pathlib import Path


def main():
    multiprocessing.freeze_support()
    args = sys.argv[1:]
    if args and args[0] == '--check-window':
        sys.argv = [sys.argv[0], *args[1:]]
        from lab.check_window import main as check_window
        return check_window()
    if args and args[0] == "--can-update":
        import psutil
        executable = Path(sys.executable).resolve()
        for process in psutil.process_iter(['exe']):
            try:
                if process.pid != os.getpid() and process.info['exe'] and Path(process.info['exe']).resolve() == executable:
                    return 2
            except (psutil.Error, OSError):
                logging.debug('Could not inspect process during update check', exc_info=True)
        return 0
    if args and args[0] == "--uninstall-integration":
        from ember.autostart import stop_watcher, uninstall
        stop_watcher()
        uninstall()
        if os.name == "nt":
            from ember.millennium import remove_owned_adapter
            remove_owned_adapter()
        return 0
    if args and args[0] == "--enable-integration":
        os.environ["EMBER_MODE"] = "desktop"
        from ember.config import steam_path
        from ember.autostart import install
        install(steam_path())
        return 0
    if args and args[0] == "--watch-steam":
        from ember.autostart import main as watch
        return watch()
    backend = bool(args and args[0] == "--backend")
    if backend:
        sys.argv = [sys.argv[0], *args[1:]]
    elif args and args[0] == "--millennium-bootstrap":
        from ember.millennium_bootstrap import main as bootstrap
        return bootstrap()
    else:
        from ember.desktop import main as desktop
        return desktop()
    from ember.config import DATA
    os.environ["EMBER_DATA_DIR"] = str(DATA)
    log = open(DATA / "runtime-console.log", "a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = log
    if sys.stderr is None:
        sys.stderr = log
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s",
                        handlers=[logging.FileHandler(DATA / "ember.log", encoding="utf-8"), logging.StreamHandler(sys.stdout)])
    faulthandler.enable(file=log)
    from ember.core import main as runtime
    return runtime()


def run():
    try:
        return main()
    except Exception as error:
        from ember.host import desktop_data
        folder = desktop_data()
        folder.mkdir(parents=True, exist_ok=True)
        import traceback
        with open(folder / "startup-error.log", "a", encoding="utf-8") as output:
            traceback.print_exc(file=output)
        if not any(flag in sys.argv for flag in ("--backend", "--millennium-bootstrap", "--watch-steam", "--attach")) and os.name == "nt":
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, f"{error}\n\n{folder / 'startup-error.log'}", "Ember", 16)
        if os.name != "nt":
            print(f"Ember: {error}\nЖурнал: {folder / 'startup-error.log'}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
