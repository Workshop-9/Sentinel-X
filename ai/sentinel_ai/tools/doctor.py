"""Diagnostic avant démo : python -m sentinel_ai doctor"""
from __future__ import annotations

import importlib
import logging
import platform
import socket
from typing import Callable

from ..config import ENV_FILE, Settings
from ..paths import REPO_DIR, is_writable, resolve, workdir

log = logging.getLogger(__name__)
OK, WARN, FAIL = "OK  ", "WARN", "FAIL"


def _check(name: str, fn: Callable[[], tuple[str, str]], results: list) -> None:
    try:
        status, detail = fn()
    except Exception as exc:  # un diagnostic ne doit jamais planter
        status, detail = FAIL, f"{type(exc).__name__}: {exc}"
    results.append((status, name, detail))
    level = {OK: logging.INFO, WARN: logging.WARNING, FAIL: logging.ERROR}[status]
    log.log(level, "[%s] %-26s %s", status, name, detail)


def run(settings: Settings) -> bool:
    results: list[tuple[str, str, str]] = []

    def python():
        v = platform.python_version()
        return (OK if tuple(map(int, v.split(".")[:2])) >= (3, 11) else FAIL), v

    def libs():
        missing, versions = [], []
        for mod in ("numpy", "pandas", "sklearn", "joblib", "paho.mqtt", "cv2", "matplotlib"):
            try:
                m = importlib.import_module(mod)
                versions.append(f"{mod.split('.')[0]} {getattr(m, '__version__', '?')}")
            except ImportError:
                missing.append(mod)
        if missing:
            return FAIL, "manquant : " + ", ".join(missing) + " → pip install -r requirements.txt"
        return OK, ", ".join(versions)

    def ultralytics():
        importlib.import_module("ultralytics")
        w = resolve(settings.vision.weights)
        return (OK, f"poids {w.name} présents") if w.exists() else (FAIL, f"poids absents : {w}")

    def writable():
        if is_writable(REPO_DIR):
            return OK, f"sorties dans {REPO_DIR}"
        return WARN, (f"ai/ protégé par Windows → sorties dans {workdir()} "
                      "(autoriser python.exe dans « Contrôle d'accès aux dossiers »)")

    def model():
        from ..anomaly.registry import load_production
        b = load_production(settings.paths.artifacts_dir)
        return OK, f"{b.version} ({b.algorithm}), intégrité SHA-256 vérifiée"

    def secrets():
        m = settings.mqtt
        if m.has_credentials:
            return OK, f"utilisateur MQTT « {m.username} » (depuis {'.env' if ENV_FILE.exists() else 'environnement'})"
        return FAIL, "SENTINEL_MQTT_USER / SENTINEL_MQTT_PASS absents → copier .env.example en .env"

    def ca():
        if not settings.mqtt.tls:
            return WARN, "TLS désactivé (mqtt.tls = false) : flux NON chiffré"
        p = resolve(settings.mqtt.ca_cert)
        return (OK, str(p)) if p.exists() else (FAIL, f"introuvable : {p}")

    def broker():
        m = settings.mqtt
        with socket.create_connection((m.host, m.port), timeout=3):
            return OK, f"{m.host}:{m.port} joignable"

    def stream():
        s = settings.vision.stream
        if s.host in ("127.0.0.1", "localhost"):
            return OK, f"flux vidéo limité à cette machine ({s.host}:{s.port})"
        if s.token:
            return OK, f"flux exposé sur {s.host}:{s.port}, protégé par jeton"
        return WARN, f"flux exposé sur {s.host}:{s.port} SANS jeton"

    def git_hygiene():
        gi = REPO_DIR / ".gitignore"
        needed = [".env", "certs/", "*.pt"]
        text = gi.read_text(encoding="utf-8") if gi.exists() else ""
        miss = [n for n in needed if n not in text]
        return (OK, "secrets et poids exclus de Git") if not miss else (FAIL, f".gitignore incomplet : {miss}")

    for name, fn in [("Python", python), ("Bibliothèques", libs), ("YOLO", ultralytics),
                     ("Écriture des fichiers", writable), ("Modèle anomalies", model),
                     ("Identifiants MQTT", secrets), ("Certificat CA", ca),
                     ("Broker MQTT", broker), ("Flux vidéo", stream), ("Hygiène Git", git_hygiene)]:
        _check(name, fn, results)

    fails = sum(1 for s, _, _ in results if s == FAIL)
    log.info("Diagnostic : %d OK, %d avertissement(s), %d échec(s)",
             sum(1 for s, _, _ in results if s == OK), sum(1 for s, _, _ in results if s == WARN), fails)
    return fails == 0
