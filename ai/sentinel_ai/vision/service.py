"""Boucle vision : webcam -> YOLO -> confirmation -> alerte MQTT + photo + flux dashboard."""
from __future__ import annotations

import json
import logging
import platform
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import cv2

from ..config import Settings
from ..paths import resolve
from .detector import PersonDetector, TemporalConfirm
from .stream import FrameStore, StreamServer

log = logging.getLogger(__name__)

WINDOW_TITLE = "Sentinel-X - Vision IA"
RED, GREEN = (0, 0, 255), (0, 200, 0)


def open_camera(index: int | None, source: str | None) -> cv2.VideoCapture:
    if source:
        return cv2.VideoCapture(source)

    camera_index = 0 if index is None else index
    if platform.system() == "Windows" and hasattr(cv2, "CAP_DSHOW"):
        return cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
    return cv2.VideoCapture(camera_index)


def cleanup_captures(directory: Path, days: int) -> int:
    """RGPD : supprime les photos d'intrus plus anciennes que `days` jours."""
    if days <= 0 or not directory.exists():
        return 0
    limit = time.time() - days * 86400
    removed = 0
    for p in directory.glob("intrus_*.jpg"):
        if p.stat().st_mtime < limit:
            p.unlink(missing_ok=True)
            removed += 1
    return removed


def connect_mqtt(settings: Settings):
    """MQTT optionnel : si indisponible, la détection continue sans envoyer d'alerte."""
    from .. import mqtt as mq
    try:
        client = mq.create_client(settings, "vision")
        log_connect = mq.on_connect_logger("vision")

        def on_connect(c, userdata, flags, reason_code, properties):
            log_connect(c, userdata, flags, reason_code, properties)
            if not reason_code.is_failure:
                mq.announce_online(c)

        client.on_connect = on_connect
        mq.connect(client, settings)
        client.loop_start()
        return client
    except (mq.MqttConfigError, ConnectionError) as exc:
        log.warning("MQTT indisponible, détection en local uniquement : %s", exc)
        return None


class AlertManager:
    def __init__(self, settings: Settings, client, capture_dir: Path):
        self.settings = settings
        self.client = client
        self.capture_dir = capture_dir
        self.last_alert = 0.0
        self.count = 0

    def ready(self) -> bool:
        return time.time() - self.last_alert >= self.settings.vision.cooldown_s

    def send(self, image, persons: int, confidence: float, inference_ms: float) -> None:
        self.last_alert = time.time()
        self.count += 1
        now = datetime.now(timezone.utc)
        snapshot = f"intrus_{now:%Y%m%d_%H%M%S}.jpg"
        try:
            self.capture_dir.mkdir(parents=True, exist_ok=True)
            if not cv2.imwrite(str(self.capture_dir / snapshot), image):
                snapshot = ""
        except OSError as exc:
            log.warning("Photo non enregistrée : %s", exc)
            snapshot = ""

        device = self.settings.device_id
        alert = {
            "device_id": device,
            "source": "vision",
            "type": "intrusion",
            "severity": "high",
            "confidence": round(confidence, 2),
            "persons": persons,
            "inference_ms": round(inference_ms, 1),
            "snapshot": snapshot,
            "ts": now.isoformat(timespec="seconds"),
        }
        if self.client:
            self.client.publish(self.settings.topic("vision", device), json.dumps(alert), qos=1)
            if self.settings.vision.auto_alarm:
                self.client.publish(self.settings.topic("cmd", device), json.dumps({"alarm": "on"}), qos=1)
        log.warning("INTRUS détecté : %d personne(s), confiance %.0f %% → %s%s", persons,
                    100 * confidence, snapshot or "(pas de photo)",
                    "" if self.client else " (alerte non envoyée : MQTT hors ligne)")


def run(settings: Settings, camera: int | None = None, source: str | None = None,
        headless: bool = False, stream: bool | None = None) -> None:
    v = settings.vision
    capture_dir = resolve(settings.paths.captures_dir)
    removed = cleanup_captures(capture_dir, v.captures_retention_days)
    if removed:
        log.info("%d photo(s) de plus de %d jours supprimée(s) (RGPD)", removed,
                 v.captures_retention_days)

    detector = PersonDetector(resolve(v.weights), v.conf_min, imgsz=max(v.frame_width, v.frame_height))
    confirm = TemporalConfirm(v.confirm_frames, v.confirm_window)
    client = connect_mqtt(settings)
    alerts = AlertManager(settings, client, capture_dir)

    store = FrameStore()
    server = None
    if (v.stream.enabled if stream is None else stream):
        s = v.stream
        server = StreamServer(store, s.host, s.port, s.token, s.max_clients, s.fps).start()

    index = v.camera_index if camera is None else camera
    cap = open_camera(index, source)
    if not cap.isOpened():
        raise RuntimeError(f"Caméra {index} introuvable : lance « python -m sentinel_ai cameras »")
    show = v.show_window and not headless
    log.info("Surveillance en cours (caméra %s)%s", source or index,
             " — touche q pour quitter" if show else " — Ctrl+C pour quitter")

    times: deque[float] = deque(maxlen=30)
    latencies: deque[float] = deque(maxlen=30)
    failures = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                if source:                       # fin du fichier vidéo
                    break
                failures += 1
                if failures > 5:
                    raise RuntimeError("La webcam ne renvoie plus d'image (débranchée ?)")
                log.warning("Image non reçue, nouvelle tentative (%d/5)", failures)
                time.sleep(1)
                cap.release()
                cap = open_camera(index, source)
                continue
            failures = 0
            frame = cv2.resize(frame, (v.frame_width, v.frame_height))   # < 100 ms par image

            det = detector(frame)
            present = confirm.update(det.persons > 0)
            times.append(time.perf_counter())
            latencies.append(det.inference_ms)
            fps = (len(times) - 1) / (times[-1] - times[0]) if len(times) > 1 else 0.0
            avg_ms = sum(latencies) / len(latencies)

            image = det.annotated
            text, color = (f"INTRUS x{det.persons}", RED) if present else ("RAS", GREEN)
            cv2.putText(image, f"{text} | {det.inference_ms:.0f} ms | {fps:.1f} FPS", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

            if present and alerts.ready():
                alerts.send(image, det.persons, det.confidence, det.inference_ms)

            ok_jpg, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ok_jpg:
                store.update(buf.tobytes(), persons=det.persons, intrusion=present,
                             confidence=round(det.confidence, 2), inference_ms=round(avg_ms, 1),
                             fps=round(fps, 1), alerts=alerts.count,
                             mqtt=bool(client and client.is_connected()))
            if show:
                cv2.imshow(WINDOW_TITLE, image)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    except KeyboardInterrupt:
        pass
    finally:
        log.info("Arrêt de la vision — %d alerte(s) envoyée(s)", alerts.count)
        cap.release()
        if show:
            cv2.destroyAllWindows()
        if server:
            server.stop()
        if client:
            from .. import mqtt as mq
            mq.announce_offline(client)
            client.loop_stop()
            client.disconnect()
