# Ember — Copyright (C) 2026 Ember contributors.
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details (LICENSE).

import os
import logging
import subprocess
import sys
import time
from pathlib import Path

project = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project))

def main():
    from ember.desktop import live_runtime, request_quit
    data = Path(os.environ["LOCALAPPDATA"]) / "Ember/Desktop"
    data.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=data / "bootstrap.log", level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    existing = live_runtime(data)
    if existing and existing.get("integration") != "millennium":
        request_quit(existing)
        existing = None
    if not existing:
        environment = dict(os.environ)
        environment.pop("PYTHONHOME", None)
        from ember.launch import install_root, launch_command
        logging.info("Starting Ember for Millennium")
        with (data / "bootstrap-console.log").open("a", encoding="utf-8") as output:
            child = subprocess.Popen(launch_command("--millennium", "--no-open"), cwd=install_root(), env=environment,
                                     stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            ready = live_runtime(data)
            if ready and ready.get("integration") == "millennium":
                logging.info("Ember is ready for authenticated requests")
                return
            if child.poll() not in (None, 0):
                raise RuntimeError("Ember could not start. See bootstrap-console.log and startup-error.log.")
            time.sleep(.2)
        raise TimeoutError("Ember did not become ready within 20 seconds. See bootstrap.log and startup-error.log.")


if __name__ == "__main__":
    main()
