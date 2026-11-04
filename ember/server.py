# Ember — Copyright (C) 2026 Ember contributors.
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details (LICENSE).

import hmac
import json
import logging
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from ember import VERSION
from ember.config import ROOT
from ember.store_additions import StoreAdditions

logger = logging.getLogger(__name__)


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, dispatcher, stream, token, port=0, mode="desktop"):
        self.dispatcher = dispatcher
        self.stream = stream
        self.token = token
        self.mode = mode
        self.integration = {"connected": False, "mode": "standalone", "message": "Ожидание Steam"}
        self.store_additions = StoreAdditions()
        super().__init__(("127.0.0.1", port), Handler)

    @property
    def origin(self):
        return f"http://127.0.0.1:{self.server_port}"

    def start(self):
        threading.Thread(target=self.serve_forever, name="ember-http", daemon=True).start()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        logger.debug("HTTP %s %s", self.command, urlsplit(self.path).path)

    def _reply(self, status, body, content_type="application/json; charset=utf-8"):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            logger.debug("Client disconnected")

    def _authorized(self):
        expected = "Bearer " + self.server.token
        return hmac.compare_digest(self.headers.get("Authorization", "").encode("utf-8"), expected.encode("ascii"))

    def _valid_host(self):
        return self.headers.get("Host", "") == f"127.0.0.1:{self.server.server_port}"

    def do_GET(self):
        if not self._valid_host():
            return self._reply(403, {"error": "Invalid host"})
        uri = urlsplit(self.path)
        if uri.path == "/health":
            return self._reply(200, {"product": "Ember", "version": VERSION})
        if uri.path.startswith("/api/"):
            if not self._authorized():
                return self._reply(401, {"error": "Authentication required"})
            if uri.path == "/api/info":
                return self._reply(200, {"version": VERSION, "mode": self.server.mode, "cursor": self.server.stream.cursor, "methods": sorted(self.server.dispatcher.methods), "signals": sorted(self.server.dispatcher.signals), "integration": self.server.integration})
            if uri.path == "/api/store-add":
                request_id = parse_qs(uri.query).get("request_id", [None])[0]
                return self._reply(200, self.server.store_additions.status(request_id) if request_id else {"request": self.server.store_additions.pending()})
            if uri.path == "/api/events":
                try:
                    after = max(0, int(parse_qs(uri.query).get("after", [0])[0]))
                except ValueError:
                    return self._reply(400, {"error": "Invalid event cursor"})
                return self._reply(200, self.server.stream.read(after))
            return self._reply(404, {"error": "Unknown endpoint"})
        if uri.path == "/LICENSE":
            file = ROOT / "LICENSE"
        elif uri.path == "/NOTICES":
            file = ROOT / "EMBER-NOTICES.txt"
        elif uri.path.startswith("/lab/"):
            file = ROOT / "lab/web" / unquote(uri.path[len("/lab/"):])
            if not file.resolve().is_relative_to((ROOT / "lab/web").resolve()):
                return self._reply(403, {"error": "Invalid path"})
        elif uri.path.startswith("/ember/"):
            file = ROOT / "ember" / "web" / unquote(uri.path[len("/ember/"):])
            if not file.resolve().is_relative_to((ROOT / "ember/web").resolve()):
                return self._reply(403, {"error": "Invalid path"})
        else:
            relative = unquote(uri.path).lstrip("/") or "index.html"
            file = ROOT / "sff/webui" / relative
            if not file.resolve().is_relative_to((ROOT / "sff/webui").resolve()):
                return self._reply(403, {"error": "Invalid path"})
        if not file.is_file():
            return self._reply(404, {"error": "File not found"})
        body = file.read_bytes()
        content_type = mimetypes.guess_type(str(file))[0] or "application/octet-stream"
        if file.suffix in (".html", ".js", ".css", ".txt"):
            content_type += "; charset=utf-8"
        if file == ROOT / "sff/webui/index.html":
            html = body.decode("utf-8").replace('src="qrc:///qtwebchannel/qwebchannel.js"', 'src="/ember/transport.js"')
            html = html.replace("SteaMidra", "Ember")
            html = html.replace('<link rel="stylesheet" href="css/premium.css?v=668d">', '')
            html = html.replace('src="assets/SFF.png"', 'src="/ember/mark.svg"')
            html = html.replace("</head>", '<link rel="stylesheet" href="/ember/ember.css"></head>')
            html = html.replace("</body>", '<script src="/ember/ember.js"></script></body>')
            body = html.encode("utf-8")
        self._reply(200, body, content_type)

    def do_POST(self):
        if not self._valid_host() or not self._authorized():
            return self._reply(401, {"error": "Authentication required"})
        if self.headers.get("Origin") not in (None, self.server.origin):
            return self._reply(403, {"error": "Invalid origin"})
        path = urlsplit(self.path).path
        if path not in ("/api/call", "/api/store-add"):
            return self._reply(404, {"error": "Unknown endpoint"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 24 * 1024 * 1024:
                raise ValueError("Invalid request size")
            payload = json.loads(self.rfile.read(length))
            if path == "/api/store-add":
                if payload.get("action") == "acknowledge":
                    return self._reply(200, {"success": self.server.store_additions.acknowledge(payload.get("request_id"))})
                if payload.get("action") == "request":
                    return self._reply(200, self.server.store_additions.request(payload.get("app_id"), payload.get("name")))
                raise ValueError("Invalid store action")
            result = self.server.dispatcher.call(payload["method"], payload.get("args", []))
            self._reply(200, {"result": result})
        except PermissionError as error:
            self._reply(403, {"error": str(error)})
        except TimeoutError as error:
            self._reply(504, {"error": str(error)})
        except (KeyError, ValueError, TypeError) as error:
            self._reply(400, {"error": str(error)})
        except Exception as error:
            logger.warning("RPC request failed: %s", type(error).__name__)
            self._reply(500, {"error": str(error)})
