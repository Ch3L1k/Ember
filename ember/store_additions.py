# Ember — Copyright (C) 2026 Ember contributors.
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details (LICENSE).

import logging
import re
import secrets
import threading
import time

logger = logging.getLogger(__name__)


class StoreAdditions:
    def __init__(self):
        self._lock = threading.Lock()
        self._pending = None
        self._opened = []

    def _expire(self):
        if self._pending and time.time() - self._pending["created"] >= 60:
            logger.debug("Store handoff expired for app %s", self._pending["app_id"])
            self._pending = None

    def pending(self):
        with self._lock:
            self._expire()
            return dict(self._pending) if self._pending else None

    def request(self, app_id, name):
        if not isinstance(app_id, str) or not re.fullmatch(r"[1-9][0-9]{0,9}", app_id) or int(app_id) > 4294967295:
            return {"success": False, "error": "invalid_app"}
        if not isinstance(name, str) or len(name) > 512:
            name = "App " + app_id
        name = re.sub(r"[\x00-\x1f\x7f]", " ", name).strip() or "App " + app_id
        with self._lock:
            self._expire()
            if self._pending:
                if self._pending["app_id"] == app_id:
                    return {"success": True, "request_id": self._pending["request_id"]}
                return {"success": False, "error": "busy"}
            self._pending = {"app_id": app_id, "name": name, "request_id": secrets.token_hex(12), "created": time.time()}
            logger.debug("Store handoff requested for app %s", app_id)
            return {"success": True, "request_id": self._pending["request_id"]}

    def acknowledge(self, request_id):
        with self._lock:
            self._expire()
            if self._pending and self._pending["request_id"] == request_id:
                self._opened.append(request_id)
                self._opened = self._opened[-64:]
                self._pending = None
                return True
            return request_id in self._opened

    def status(self, request_id):
        with self._lock:
            self._expire()
            return {"state": "opened" if request_id in self._opened else "waiting" if self._pending and self._pending["request_id"] == request_id else "expired"}
