# Ember — Copyright (C) 2026 Ember contributors.
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details (LICENSE).

import collections
import concurrent.futures
import logging
import threading
import time

from PyQt6.QtCore import QObject, QMetaMethod, Qt, pyqtSignal, pyqtSlot

logger = logging.getLogger(__name__)


class EventStream:
    def __init__(self):
        self._condition = threading.Condition()
        self._events = collections.deque(maxlen=1500)
        self._cursor = 0

    def publish(self, name, args):
        with self._condition:
            self._cursor += 1
            self._events.append({"id": self._cursor, "name": name, "args": args})
            self._condition.notify_all()

    @property
    def cursor(self):
        with self._condition:
            return self._cursor

    def read(self, after, timeout=20):
        deadline = time.monotonic() + timeout
        with self._condition:
            while self._cursor == after:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._condition.wait(remaining)
            reset = after > self._cursor or bool(self._events and after < self._events[0]["id"] - 1)
            return {"cursor": self._cursor, "events": [] if reset else [e for e in self._events if e["id"] > after], "reset": reset}


class Dispatcher(QObject):
    requested = pyqtSignal(object)

    def __init__(self, bridge, stream, policy=None):
        super().__init__()
        self.bridge = bridge
        self.stream = stream
        self.policy = policy
        self.methods = set()
        self.signals = set()
        meta = bridge.metaObject()
        for index in range(QObject.staticMetaObject.methodCount(), meta.methodCount()):
            method = meta.method(index)
            name = bytes(method.name()).decode()
            if method.methodType() == QMetaMethod.MethodType.Slot:
                self.methods.add(name)
            elif method.methodType() == QMetaMethod.MethodType.Signal:
                self.signals.add(name)
        for name in self.signals:
            getattr(bridge, name).connect(lambda *args, event=name: self.stream.publish(event, list(args)))
        self.requested.connect(self._dispatch, Qt.ConnectionType.QueuedConnection)

    def call(self, method, args, timeout=180):
        if method not in self.methods:
            raise ValueError("Unknown backend method")
        if not isinstance(args, list) or len(args) > 24:
            raise ValueError("Invalid arguments")
        if self.policy is not None:
            self.policy.check(method, args)
        future = concurrent.futures.Future()
        self.requested.emit((method, args, future))
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            if future.cancel():
                raise TimeoutError("Операция не была запущена: время ожидания истекло.")
            raise TimeoutError("Операция ещё выполняется. Не повторяйте её до завершения.")

    @pyqtSlot(object)
    def _dispatch(self, request):
        method, args, future = request
        if not future.set_running_or_notify_cancel():
            logger.debug("Skipped expired backend request: %s", method)
            return
        try:
            result = getattr(self.bridge, method)(*args)
            future.set_result(result)
        except Exception as error:
            logger.exception("Backend method failed: %s", method)
            future.set_exception(error)
