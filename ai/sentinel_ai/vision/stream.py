"""Serveur vidéo MJPEG pour le dashboard, durci pour le pentest.

* écoute sur 127.0.0.1 par défaut (pas exposé au réseau) ;
* jeton optionnel (?token=... ou en-tête Authorization: Bearer ...), comparé en temps constant ;
* nombre de clients simultanés limité (anti-saturation), délai d'inactivité ;
* aucune bannière de version (Server: SentinelX) ;
* routes : /video (flux), /snapshot.jpg (image), /health (état JSON).
"""
from __future__ import annotations

import hmac
import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

log = logging.getLogger(__name__)


class FrameStore:
    """Dernière image JPEG + statistiques, partagées entre la boucle vision et le serveur."""

    def __init__(self):
        self._lock = threading.Lock()
        self._jpeg: bytes | None = None
        self._stats: dict[str, Any] = {}

    def update(self, jpeg: bytes, **stats: Any) -> None:
        with self._lock:
            self._jpeg = jpeg
            self._stats = {**stats, "updated": time.time()}

    def get(self) -> tuple[bytes | None, dict[str, Any]]:
        with self._lock:
            return self._jpeg, dict(self._stats)


def make_handler(store: FrameStore, token: str, slots: threading.BoundedSemaphore, fps: float):
    period = 1.0 / max(fps, 1.0)

    class Handler(BaseHTTPRequestHandler):
        server_version = "SentinelX"
        sys_version = ""
        timeout = 15

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self._security_headers()
            self.end_headers()
            self.wfile.write(body)

        def _security_headers(self) -> None:
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")

        def _authorized(self, query: dict[str, list[str]]) -> bool:
            if not token:
                return True
            given = query.get("token", [""])[0]
            auth = self.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                given = auth[7:]
            return hmac.compare_digest(given.encode(), token.encode())

        def do_GET(self) -> None:  # noqa: N802 (API http.server)
            url = urlparse(self.path)
            if not self._authorized(parse_qs(url.query)):
                self._send(401, b"unauthorized", "text/plain")
                return
            if url.path == "/health":
                _, stats = store.get()
                self._send(200, json.dumps(stats).encode(), "application/json")
            elif url.path == "/snapshot.jpg":
                jpeg, _ = store.get()
                if jpeg is None:
                    self._send(503, b"no frame yet", "text/plain")
                else:
                    self._send(200, jpeg, "image/jpeg")
            elif url.path == "/video":
                self._stream()
            else:
                self._send(404, b"not found", "text/plain")

        def _stream(self) -> None:
            if not slots.acquire(blocking=False):
                self._send(503, b"too many clients", "text/plain")
                return
            try:
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self._security_headers()
                self.end_headers()
                last = None
                while True:
                    jpeg, _ = store.get()
                    if jpeg is not None and jpeg is not last:
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n"
                                         + f"Content-Length: {len(jpeg)}\r\n\r\n".encode()
                                         + jpeg + b"\r\n")
                        last = jpeg
                    time.sleep(period)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError):
                pass
            finally:
                slots.release()

        def log_message(self, fmt: str, *args: Any) -> None:
            log.debug("%s %s", self.client_address[0], fmt % args)

    return Handler


class StreamServer:
    def __init__(self, store: FrameStore, host: str, port: int, token: str = "",
                 max_clients: int = 4, fps: float = 10):
        handler = make_handler(store, token, threading.BoundedSemaphore(max_clients), fps)
        self.httpd = ThreadingHTTPServer((host, port), handler)
        self.httpd.daemon_threads = True
        self.host, self.port, self.token, self.max_clients = host, port, token, max_clients

    @property
    def url(self) -> str:
        host = "localhost" if self.host in ("127.0.0.1", "0.0.0.0") else self.host
        suffix = "?token=<SENTINEL_STREAM_TOKEN>" if self.token else ""
        return f"http://{host}:{self.port}/video{suffix}"

    def start(self) -> "StreamServer":
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        if self.host not in ("127.0.0.1", "localhost") and not self.token:
            log.warning("Flux vidéo exposé sur %s SANS jeton : définis SENTINEL_STREAM_TOKEN", self.host)
        log.info("Flux vidéo : %s (max %d clients, aussi /snapshot.jpg et /health)",
                 self.url, self.max_clients)
        return self

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
