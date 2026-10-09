"""Service temps réel : télémétrie MQTT -> détecteur -> topic anomaly (+ alarme du boîtier)."""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from ..config import Settings
from ..data.schema import device_from_topic, parse_reading
from .detector import AnomalyDetector
from .models import ModelBundle

log = logging.getLogger(__name__)

Message = tuple[str, str, int, bool]       # topic, payload, qos, retain


class AnomalyService:
    """Logique métier sans réseau (testable) : un message entrant -> messages à publier."""

    def __init__(self, settings: Settings, bundle: ModelBundle, auto_alarm: bool | None = None):
        self.settings = settings
        self.bundle = bundle
        live = settings.anomaly.live
        self.auto_alarm = live.auto_alarm if auto_alarm is None else auto_alarm
        self.detectors: dict[str, AnomalyDetector] = {}
        self.invalid = 0
        self.processed = 0

    def detector(self, device: str) -> AnomalyDetector:
        if device not in self.detectors:
            live = self.settings.anomaly.live
            self.detectors[device] = AnomalyDetector(self.bundle, live.consecutive, live.max_freeze)
            log.info("Nouveau boîtier suivi : %s (fenêtre de %d s avant le premier score)",
                     device, (self.bundle.feature_params["window"] + 1) * 2)
        return self.detectors[device]

    def handle(self, topic: str, payload: bytes | str, now: float | None = None) -> list[Message]:
        try:
            data = json.loads(payload)
        except (json.JSONDecodeError, UnicodeDecodeError):
            data = None
        reading = (parse_reading(data, self.settings.device_id, device_from_topic(topic))
                   if isinstance(data, dict) else None)
        if reading is None:
            self.invalid += 1
            if self.invalid % 10 == 1:
                log.warning("Message ignoré (mesure absente ou hors plage) sur %s : %.80s",
                            topic, payload)
            return []

        now = time.time() if now is None else now
        det = self.detector(reading.device_id)
        decision = det.step(reading.temp, reading.hum, reading.gas, t=now)
        if decision is None:
            log.info("[%s] Remplissage de la fenêtre %d/%d", reading.device_id,
                     len(det.extractor.buffer), det.extractor.buffer.maxlen)
            return []

        self.processed += 1
        result: dict[str, Any] = {
            "device_id": reading.device_id,
            "ts": datetime.fromtimestamp(now, timezone.utc).isoformat(timespec="seconds"),
            "score": round(decision.score, 4),
            "is_anomaly": decision.is_anomaly,
            "streak": decision.streak,
            "level": decision.level,
            "causes": [c["label"] for c in decision.causes],
            "model": self.bundle.version,
        }
        out: list[Message] = [(self.settings.topic("anomaly", reading.device_id),
                               json.dumps(result, ensure_ascii=False), 0, False)]

        icon = {"normal": "OK  ", "suspect": "??  ", "alarm": "ALARME"}[decision.level]
        causes = f" — {', '.join(result['causes'])}" if result["causes"] else ""
        log.info("[%s] %s score=%+.3f streak=%d%s", reading.device_id, icon, decision.score,
                 decision.streak, causes)

        if decision.alarm_triggered and self.auto_alarm:
            out.append((self.settings.topic("cmd", reading.device_id),
                        json.dumps({"alarm": "on"}), 1, False))
            log.warning("[%s] Anomalie confirmée (%d mesures d'affilée) : sirène déclenchée",
                        reading.device_id, decision.streak)
        return out


def run(settings: Settings, auto_alarm: bool | None = None) -> None:
    from .. import mqtt as mq
    from .registry import load_production

    bundle = load_production(settings.paths.artifacts_dir)
    service = AnomalyService(settings, bundle, auto_alarm)
    client = mq.create_client(settings, "anomaly")
    log_connect = mq.on_connect_logger("anomaly")

    def on_connect(c, userdata, flags, reason_code, properties):
        log_connect(c, userdata, flags, reason_code, properties)
        if not reason_code.is_failure:
            c.subscribe(settings.mqtt.topic_telemetry, qos=0)
            mq.announce_online(c)
            log.info("Écoute de %s — alarme automatique : %s", settings.mqtt.topic_telemetry,
                     "oui" if service.auto_alarm else "non")

    def on_message(c, userdata, msg):
        try:
            for topic, payload, qos, retain in service.handle(msg.topic, msg.payload):
                c.publish(topic, payload, qos=qos, retain=retain)
        except Exception:  # un message malformé ne doit jamais arrêter le service
            log.exception("Erreur de traitement du message %s", msg.topic)

    client.on_connect = on_connect
    client.on_message = on_message
    mq.connect(client, settings)
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        log.info("Arrêt demandé — %d mesures analysées", service.processed)
    finally:
        mq.announce_offline(client)
        client.disconnect()
