# Ember — Copyright (C) 2026 Ember contributors.
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details (LICENSE).

import ctypes
import logging
import os
from pathlib import Path
from ctypes import wintypes

from PyQt6.QtCore import QByteArray, QObject, Qt, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QDesktopServices, QIcon, QPainter, QPainterPath, QPen, QRegion
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QMainWindow, QSizeGrip, QToolButton, QVBoxLayout, QWidget

from ember.config import ROOT

logger = logging.getLogger(__name__)


class WindowActions(QObject):
    open_requested = pyqtSignal()


def steam_window():
    if os.name != "nt":
        return None
    import psutil
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    handles = []

    @callback_type
    def collect(hwnd, _):
        if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, 4):
            return True
        title = ctypes.create_unicode_buffer(user32.GetWindowTextLengthW(hwnd) + 1)
        user32.GetWindowTextW(hwnd, title, len(title))
        if title.value != "Steam":
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        try:
            if psutil.Process(pid.value).name().lower() in {"steam.exe", "steamwebhelper.exe"}:
                handles.append(hwnd)
        except psutil.Error:
            logger.debug("Steam owner window disappeared")
        return True

    user32.EnumWindows(collect, 0)
    return handles[0] if handles else None


class LocalPage(QWebEnginePage):
    def __init__(self, profile, parent, origin):
        super().__init__(profile, parent)
        self.origin = origin

    def acceptNavigationRequest(self, url, kind, main_frame):
        if url.toString().startswith(self.origin + "/") or url.scheme() == "about":
            return True
        if main_frame and kind == QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
            QDesktopServices.openUrl(url)
        return False

    def createWindow(self, _kind):
        page = QWebEnginePage(self.profile(), self)
        def open_external(url):
            if url.isEmpty() or url.scheme() == "about":
                return
            QDesktopServices.openUrl(url)
            page.deleteLater()
        page.urlChanged.connect(open_external)
        return page


class CaptionButton(QToolButton):
    def __init__(self, kind, caption, parent):
        super().__init__(parent)
        self.kind = kind
        self.setObjectName("ember-" + kind)
        self.setAccessibleName(caption)
        self.setToolTip(caption)
        self.setFixedSize(32, 30)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setStyleSheet("QToolButton { border: 0; background: transparent; } QToolButton:hover { background: #323943; }")

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#b8bfc5" if self.underMouse() else "#7d8c94"), 1.2))
        x, y = self.width() // 2, self.height() // 2
        if self.kind == "minimize":
            painter.drawLine(x - 6, y + 1, x + 6, y + 1)
        elif self.kind == "maximize":
            if self.window().isMaximized():
                painter.drawRect(x - 3, y - 5, 9, 8)
                painter.fillRect(x - 6, y - 2, 9, 8, QColor("#171d25"))
                painter.drawRect(x - 6, y - 2, 9, 8)
            else:
                painter.drawRect(x - 5, y - 5, 11, 10)
        else:
            painter.drawLine(x - 5, y - 5, x + 5, y + 5)
            painter.drawLine(x - 5, y + 5, x + 5, y - 5)


class CaptionBar(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.drag_offset = None
        self.setFixedHeight(30)
        self.setObjectName("EmberCaption")
        self.setStyleSheet("#EmberCaption { background: #171d25; }")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        sidebar_cap = QWidget(self)
        sidebar_cap.setFixedWidth(196)
        sidebar_cap.setFixedHeight(30)
        sidebar_cap.setStyleSheet("background: #2a2d34;")
        sidebar_cap.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(sidebar_cap)
        layout.addStretch()
        self.minimize = CaptionButton("minimize", "Свернуть", self)
        self.maximize = CaptionButton("maximize", "Развернуть / восстановить", self)
        self.close_button = CaptionButton("close", "Закрыть", self)
        self.minimize.clicked.connect(window.showMinimized)
        self.maximize.clicked.connect(window.toggle_maximize)
        self.close_button.clicked.connect(window.close)
        for button in (self.minimize, self.maximize, self.close_button):
            layout.addWidget(button)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if not self.window.windowHandle().startSystemMove():
                logger.debug("System window movement unavailable; using pointer movement")
                self.drag_offset = event.globalPosition().toPoint() - self.window.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.window.move(event.globalPosition().toPoint() - self.drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.window.toggle_maximize()


class EmberWindow(QMainWindow):
    def __init__(self, origin, token, attach_to_steam=True, state_path=None):
        super().__init__()
        self.attach_to_steam = attach_to_steam
        self.owner_handle = None
        self._positioned = False
        self.state_path = Path(state_path) if state_path else None
        self.setWindowTitle("Ember")
        self.setObjectName("EmberNativeWindow")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowIcon(QIcon(str(ROOT / "ember/web/mark.svg")))
        self.resize(850, 724)
        self.setMinimumSize(760, 520)
        self.setStyleSheet("QMainWindow { background: transparent; }")
        self.frame = QFrame(self)
        self.frame.setObjectName("EmberFrame")
        self.frame.setStyleSheet("#EmberFrame { background: #171d25; border: 1px solid #43505a; border-radius: 8px; }")
        self.frame_layout = QVBoxLayout(self.frame)
        self.frame_layout.setContentsMargins(1, 1, 1, 1)
        self.frame_layout.setSpacing(0)
        self.caption = CaptionBar(self)
        self.frame_layout.addWidget(self.caption)
        self.view = QWebEngineView(self)
        self.profile = QWebEngineProfile(self)
        self.page = LocalPage(self.profile, self.view, origin)
        self.view.setPage(self.page)
        self.frame_layout.addWidget(self.view, 1)
        self.setCentralWidget(self.frame)
        self.grip = QSizeGrip(self.frame)
        self.grip.setFixedSize(16, 16)
        self.grip.setStyleSheet("background: transparent;")
        self.grip.raise_()
        self.view.setUrl(QUrl(origin + "/#token=" + token))
        if self.state_path and self.state_path.is_file():
            try:
                self._positioned = self.restoreGeometry(QByteArray.fromBase64(self.state_path.read_bytes()))
                self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
                if not self._positioned:
                    logger.warning("Saved window geometry could not be restored")
            except OSError:
                logger.warning("Saved window geometry is unavailable", exc_info=True)

    def _set_owner(self):
        if not self.attach_to_steam or os.name != "nt":
            return
        owner = steam_window()
        if not owner:
            logger.warning("Steam window is unavailable; opening Ember independently")
            return
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        hwnd = int(self.winId())
        ctypes.set_last_error(0)
        user32.SetWindowLongPtrW(hwnd, -8, owner)
        if ctypes.get_last_error():
            logger.warning("Could not assign Steam window owner: %s", ctypes.get_last_error())
            return
        self.owner_handle = owner
        try:
            dark = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(wintypes.HWND(hwnd), 20, ctypes.byref(dark), ctypes.sizeof(dark))
        except OSError:
            logger.debug("Native dark title bar is unavailable", exc_info=True)
        if not self._positioned:
            rect = wintypes.RECT()
            user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
            if user32.GetWindowRect(owner, ctypes.byref(rect)):
                ratio = self.devicePixelRatioF()
                self.move(int((rect.left + rect.right) / (2 * ratio) - self.width() / 2), max(0, int((rect.top + rect.bottom) / (2 * ratio) - self.height() / 2)))
            self._positioned = True

    @pyqtSlot()
    def open_panel(self):
        if self.isMinimized():
            if self.windowState() & Qt.WindowState.WindowMaximized:
                self.showMaximized()
            else:
                self.showNormal()
        else:
            self.show()
        self._set_owner()
        self.caption.maximize.update()
        self.raise_()
        self.activateWindow()
        logger.info("Ember native window opened; Steam owner=%s", bool(self.owner_handle))

    def toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()
        self._set_owner()
        self.caption.maximize.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "grip"):
            self.grip.move(self.width() - 19, self.height() - 19)
            self.grip.setVisible(not self.isMaximized())
            self.grip.raise_()
        if self.isMaximized():
            self.clearMask()
        else:
            shape = QPainterPath()
            shape.addRoundedRect(0, 0, self.width(), self.height(), 8, 8)
            self.setMask(QRegion(shape.toFillPolygon().toPolygon()))


    def closeEvent(self, event):
        event.ignore()
        self.save_state()
        self.hide()

    def save_state(self):
        if self.state_path:
            try:
                self.state_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.state_path.with_suffix(".tmp")
                temporary.write_bytes(bytes(self.saveGeometry().toBase64()))
                temporary.replace(self.state_path)
            except OSError:
                logger.warning("Could not save window geometry", exc_info=True)

    def shutdown(self):
        self.save_state()
        self.hide()
        self.view.setPage(None)
        self.page.deleteLater()
