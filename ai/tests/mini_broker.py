"""Broker MQTT 3.1.1 minimal, en mémoire, pour les tests d'intégration (sans TLS).

Gère CONNECT, SUBSCRIBE (+ et #), PUBLISH QoS 0/1, messages retenus, PING, DISCONNECT
et le « last will ». Ne remplace évidemment pas Mosquitto.
"""
from __future__ import annotations

import socket
import struct
import threading


def _encode_len(n: int) -> bytes:
    out = bytearray()
    while True:
        byte, n = n % 128, n // 128
        out.append(byte | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _str(data: bytes, i: int) -> tuple[bytes, int]:
    (n,) = struct.unpack_from("!H", data, i)
    return data[i + 2:i + 2 + n], i + 2 + n


def matches(filt: str, topic: str) -> bool:
    f, t = filt.split("/"), topic.split("/")
    for i, part in enumerate(f):
        if part == "#":
            return True
        if i >= len(t) or (part != "+" and part != t[i]):
            return False
    return len(f) == len(t)


class MiniBroker:
    def __init__(self, users: dict[str, str] | None = None):
        self.users = users or {}
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen()
        self.port = self.sock.getsockname()[1]
        self.lock = threading.Lock()
        self.subs: dict[socket.socket, list[str]] = {}
        self.retained: dict[str, bytes] = {}
        self.log: list[tuple[str, bytes]] = []
        self.running = True
        threading.Thread(target=self._accept, daemon=True).start()

    def stop(self) -> None:
        self.running = False
        self.sock.close()

    def _accept(self) -> None:
        while self.running:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._client, args=(conn,), daemon=True).start()

    @staticmethod
    def _read(conn: socket.socket) -> tuple[int, int, bytes] | None:
        head = conn.recv(1)
        if not head:
            return None
        mult, length = 1, 0
        while True:
            b = conn.recv(1)[0]
            length += (b & 0x7F) * mult
            mult *= 128
            if not b & 0x80:
                break
        data = b""
        while len(data) < length:
            chunk = conn.recv(length - len(data))
            if not chunk:
                return None
            data += chunk
        return head[0] >> 4, head[0] & 0x0F, data

    def _publish(self, topic: str, payload: bytes, retain: bool) -> None:
        packet_body = struct.pack("!H", len(topic.encode())) + topic.encode() + payload
        packet = bytes([0x30]) + _encode_len(len(packet_body)) + packet_body
        with self.lock:
            self.log.append((topic, payload))
            if retain:
                self.retained[topic] = payload
            targets = [c for c, filters in self.subs.items() if any(matches(f, topic) for f in filters)]
        for c in targets:
            try:
                c.sendall(packet)
            except OSError:
                pass

    def _client(self, conn: socket.socket) -> None:
        will = None
        clean = False
        try:
            while True:
                pkt = self._read(conn)
                if pkt is None:
                    break
                ptype, flags, data = pkt
                if ptype == 1:                                   # CONNECT
                    _, i = _str(data, 0)
                    cflags = data[i + 1]
                    i += 4
                    _, i = _str(data, i)                         # client id
                    if cflags & 0x04:
                        wt, i = _str(data, i)
                        wm, i = _str(data, i)
                        will = (wt.decode(), wm, bool(cflags & 0x20))
                    user = pwd = b""
                    if cflags & 0x80:
                        user, i = _str(data, i)
                    if cflags & 0x40:
                        pwd, i = _str(data, i)
                    ok = not self.users or self.users.get(user.decode()) == pwd.decode()
                    conn.sendall(bytes([0x20, 0x02, 0x00, 0x00 if ok else 0x05]))
                    if not ok:
                        break
                elif ptype == 8:                                 # SUBSCRIBE
                    pid = data[:2]
                    i, granted, new = 2, [], []
                    while i < len(data):
                        f, i = _str(data, i)
                        granted.append(min(data[i], 1))
                        i += 1
                        new.append(f.decode())
                    with self.lock:
                        self.subs.setdefault(conn, []).extend(new)
                        retained = [(t, p) for t, p in self.retained.items() if any(matches(f, t) for f in new)]
                    conn.sendall(bytes([0x90, 2 + len(granted)]) + pid + bytes(granted))
                    for t, p in retained:
                        body = struct.pack("!H", len(t.encode())) + t.encode() + p
                        conn.sendall(bytes([0x31]) + _encode_len(len(body)) + body)
                elif ptype == 3:                                 # PUBLISH
                    qos, retain = (flags >> 1) & 0x03, bool(flags & 0x01)
                    topic, i = _str(data, 0)
                    if qos:
                        pid = data[i:i + 2]
                        i += 2
                        conn.sendall(bytes([0x40, 0x02]) + pid)
                    self._publish(topic.decode(), data[i:], retain)
                elif ptype == 12:                                # PINGREQ
                    conn.sendall(bytes([0xD0, 0x00]))
                elif ptype == 10:                                # UNSUBSCRIBE
                    conn.sendall(bytes([0xB0, 0x02]) + data[:2])
                elif ptype == 14:                                # DISCONNECT
                    clean = True
                    break
        except (OSError, IndexError):
            pass
        finally:
            with self.lock:
                self.subs.pop(conn, None)
            conn.close()
            if will and not clean:
                self._publish(will[0], will[1], will[2])
