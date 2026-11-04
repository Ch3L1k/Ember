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
import subprocess
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu"
    from lab.prepare import prepare
    fixture = prepare(args.root)
    from ember.launch import install_root, launch_command
    project = install_root()
    report = Path(args.report).resolve()
    report.mkdir(parents=True, exist_ok=True)
    runtime = Path(fixture["data"]) / "runtime.json"
    runtime.unlink(missing_ok=True)
    environment = dict(os.environ)
    environment.update(EMBER_MODE="lab", EMBER_LAB_ROOT=fixture["root"], EMBER_STEAM_DIR=fixture["steam"], EMBER_DATA_DIR=fixture["data"], EMBER_CDP_PORTS="", APPDATA=str(Path(fixture["root"]) / "AppData/Roaming"), LOCALAPPDATA=str(Path(fixture["root"]) / "AppData/Local"))
    with open(report / "window-backend.log", "w", encoding="utf-8") as log:
        backend = subprocess.Popen(launch_command('--backend'), cwd=project, env=environment, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            deadline = time.monotonic() + 35
            while not runtime.exists():
                if backend.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("Window test backend failed to start")
                time.sleep(.15)
            info = json.loads(runtime.read_text(encoding="utf-8"))
            from ember.window import EmberWindow
            from PyQt6.QtCore import QTimer, Qt
            from PyQt6.QtWidgets import QApplication
            from PyQt6.QtTest import QTest
            app = QApplication(sys.argv)
            app.setQuitOnLastWindowClosed(False)
            saved_geometry = Path(fixture["root"]) / "window-test-state.bin"
            saved_geometry.unlink(missing_ok=True)
            window = EmberWindow(info["origin"], info["token"], attach_to_steam=False, state_path=saved_geometry)
            window.open_panel()
            identity = int(window.winId())
            checks = {"separate_top_level_window": window.isWindow(), "no_global_always_on_top": not bool(window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)}
            checks["integrated_frameless_caption"] = bool(window.windowFlags() & Qt.WindowType.FramelessWindowHint)
            checks["reference_window_size"] = window.size().width() == 850 and window.size().height() == 724
            state = {"phase": 0, "busy": False, "started": time.monotonic()}

            def poll():
                if time.monotonic() - state["started"] > 35:
                    app.exit(1)
                    return
                if state["busy"]:
                    return
                state["busy"] = True
                def inspected(data):
                    state["busy"] = False
                    if not data:
                        return
                    if state["phase"] == 0 and data.get("ready") and data.get("games") == "1":
                        checks["native_window_connected_to_fixture_backend"] = True
                        checks["steam_blue_accent"] = data.get("accent") == "#1a9fff"
                        checks["reference_sidebar_color"] = data.get("sidebar") == "rgb(42, 45, 52)"
                        window.grab().save(str(report / "native-home.png"))
                        window.page.runJavaScript("App.navigateTo('ember-tools')")
                        state["phase"] = 1
                    elif state["phase"] == 1 and data.get("library"):
                        checks["native_tools_navigation"] = True
                        window.grab().save(str(report / "native-tools.png"))
                        QTest.mouseClick(window.caption.maximize, Qt.MouseButton.LeftButton)
                        checks["caption_maximize"] = window.isMaximized()
                        QTest.mouseClick(window.caption.minimize, Qt.MouseButton.LeftButton)
                        window.open_panel()
                        checks["maximized_window_restores_after_minimize"] = window.isMaximized() and not window.isMinimized()
                        QTest.mouseClick(window.caption.maximize, Qt.MouseButton.LeftButton)
                        checks["caption_restore"] = not window.isMaximized()
                        QTest.mouseClick(window.caption.minimize, Qt.MouseButton.LeftButton)
                        checks["caption_minimize"] = window.isMinimized()
                        window.open_panel()
                        QTest.mouseClick(window.caption.close_button, Qt.MouseButton.LeftButton)
                        checks["close_hides_window"] = not window.isVisible()
                        window.open_panel()
                        checks["reopen_reuses_window_and_page"] = window.isVisible() and identity == int(window.winId())
                        window.resize(780, 600)
                        window.save_state()
                        restored = EmberWindow(info["origin"], info["token"], attach_to_steam=False, state_path=saved_geometry)
                        checks["window_geometry_persists_between_instances"] = restored.size() == window.size()
                        state["restored_window"] = restored
                        window.resize(850, 724)
                        window.page.runJavaScript("App.navigateTo('store')")
                        state["navigated_at"] = time.monotonic()
                        state["phase"] = 2
                    elif state["phase"] == 2 and data.get("catalog") and time.monotonic() - state["navigated_at"] > .3:
                        checks["catalog_at_reference_size"] = data.get("overflow") is False
                        window.grab().save(str(report / "native-catalog.png"))
                        window.page.runJavaScript("App.navigateTo('ember-settings')")
                        state["navigated_at"] = time.monotonic()
                        state["phase"] = 3
                    elif state["phase"] == 3 and data.get("settings") and time.monotonic() - state["navigated_at"] > .3:
                        checks["settings_at_reference_size"] = data.get("overflow") is False
                        window.grab().save(str(report / "native-settings.png"))
                        state["phase"] = 4
                        app.exit(0)
                window.page.runJavaScript("({ready:!!document.querySelector('.ember-status[data-connected=true]'),games:document.getElementById('ember-game-count')?.textContent,accent:getComputedStyle(document.documentElement).getPropertyValue('--accent').trim(),sidebar:getComputedStyle(document.querySelector('.sidebar')).backgroundColor,library:!!document.querySelector('#page-ember-tools.active #ember-tool-game')?.innerText.includes('Ember Demo'),catalog:!!document.querySelector('#page-store.active #store-grid')?.innerText.includes('Ember Puzzle'),settings:!!document.querySelector('#page-ember-settings.active'),overflow:document.getElementById('content').scrollWidth>document.getElementById('content').clientWidth})", inspected)

            timer = QTimer()
            timer.timeout.connect(poll)
            timer.start(250)
            result = app.exec()
            checks["ok"] = result == 0 and state["phase"] == 4 and all(checks.values())
            (report / "native-window-checks.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
            print(json.dumps(checks, indent=2), flush=True)
            window.shutdown()
            if state.get("restored_window"):
                state["restored_window"].shutdown()
            app.processEvents()
            return 0 if checks["ok"] else 1
        finally:
            backend.terminate()
            backend.wait(timeout=10)


if __name__ == "__main__":
    raise SystemExit(main())
