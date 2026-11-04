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
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--screenshot")
    args = parser.parse_args()
    project = Path(__file__).resolve().parent.parent
    root = Path(args.root) if args.root else Path(os.environ.get("LOCALAPPDATA", project)) / "EmberLab"
    from lab.prepare import prepare
    fixture = prepare(root)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        cdp_port = probe.getsockname()[1]
    os.environ["QTWEBENGINE_REMOTE_DEBUGGING"] = f"127.0.0.1:{cdp_port}"
    if args.smoke:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu"
    from PyQt6.QtCore import QTimer, QUrl
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWidgets import QApplication, QMainWindow

    environment = dict(os.environ)
    environment.pop("QTWEBENGINE_REMOTE_DEBUGGING", None)
    environment.update(EMBER_MODE="lab", EMBER_LAB_ROOT=fixture["root"], EMBER_STEAM_DIR=fixture["steam"], EMBER_DATA_DIR=fixture["data"], EMBER_CDP_PORTS=str(cdp_port), APPDATA=str(root / "AppData/Roaming"), LOCALAPPDATA=str(root / "AppData/Local"))
    runtime = Path(fixture["data"]) / "runtime.json"
    if runtime.exists():
        previous = json.loads(runtime.read_text(encoding="utf-8"))
        try:
            with urllib.request.urlopen(previous["origin"] + "/health", timeout=1) as response:
                if json.load(response).get("product") == "Ember":
                    raise RuntimeError("This Ember Lab directory is already in use")
        except (OSError, ValueError, KeyError):
            pass
        runtime.unlink()
    log = open(root / "desktop-backend.log", "w", encoding="utf-8")
    backend = subprocess.Popen([sys.executable, str(project / "Ember.py")], cwd=project, env=environment, stdin=subprocess.DEVNULL, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    app = QApplication(sys.argv)
    app.setApplicationName("Ember Lab")
    app.setWindowIcon(QIcon(str(project / "ember/web/mark.svg")))
    window = QMainWindow()
    window.setWindowTitle("Ember Lab — отдельная тестовая среда")
    window.resize(1440, 1000)
    popups = []

    class LabView(QWebEngineView):
        def createWindow(self, _kind):
            popup = QMainWindow(window)
            popup.setWindowTitle("Ember Lab — меню")
            popup.resize(360, 360)
            child = LabView(popup)
            popups.append(child)
            popup.setCentralWidget(child)
            child.page().windowCloseRequested.connect(popup.close)
            popup.show()
            return child

    view = LabView(window)
    window.setCentralWidget(view)
    view.setHtml('<html style="background:#171d25;color:#efad70;font:22px Arial;padding:40px">Запуск Ember Lab…</html>')
    window.show()
    state = {"loaded": False, "started": time.monotonic(), "smoke_started": None, "failed": False}

    def boot():
        if not state["loaded"] and runtime.exists():
            data = json.loads(runtime.read_text(encoding="utf-8"))
            view.setUrl(QUrl(data["origin"] + "/lab/client.html"))
            state["loaded"] = True
        if backend.poll() is not None or ((not state["loaded"] or args.smoke) and time.monotonic() - state["started"] > 45):
            state["failed"] = True
            view.setHtml('<html style="background:#171d25;color:#eee;font:18px Arial;padding:40px">Ember Lab не запустился. Подробности: desktop-backend.log в папке лаборатории.</html>')
            timer.stop()
            if args.smoke:
                app.exit(1)
        if args.smoke and state["loaded"]:
            def inspect(result):
                if result:
                    if state["smoke_started"] is None:
                        state["smoke_started"] = time.monotonic()
                        view.page().runJavaScript("document.getElementById('steam-menu').click()")
                    elif popups:
                        popups[-1].page().runJavaScript("document.getElementById('ember-steam-menuitem')?.click()")
                        def panel_ready(ready):
                            if ready and time.monotonic() - state["smoke_started"] > 5:
                                if args.screenshot:
                                    view.grab().save(args.screenshot)
                                print("Ember Lab Qt smoke passed: popup menu and embedded UI", flush=True)
                                app.exit(0)
                        view.page().runJavaScript("!!document.querySelector('#ember-steam-panel iframe')?.contentDocument?.body?.innerText.includes('Ember')", panel_ready)
            view.page().runJavaScript("!!window.__emberSteam", inspect)

    timer = QTimer()
    timer.timeout.connect(boot)
    timer.start(250)

    def cleanup():
        timer.stop()
        if backend.poll() is None:
            backend.terminate()
            try:
                backend.wait(timeout=5)
            except subprocess.TimeoutExpired:
                backend.kill()
        log.close()

    app.aboutToQuit.connect(cleanup)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
