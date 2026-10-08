"""Enregistre la télémétrie MQTT dans data/telemetry.csv (données d'entraînement)."""
from __future__ import annotations

import csv
import json
import logging
import time
from datetime import datetime

from ..config import Settings
from ..data.schema import CSV_COLUMNS, device_from_topic, parse_reading
from ..paths import resolve, workdir

log = logging.getLogger(__name__)


def run(settings: Settings, label: str, minutes: float | None = None) -> int:
    from .. import mqtt as mq

    path = resolve(settings.paths.data_dir, workdir()) / "telemetry.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists()
    fh = open(path, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
    if new_file:
        writer.writeheader()

    state = {"count": 0, "skipped": 0}
    deadline = time.time() + minutes * 60 if minutes else None
    client = mq.create_client(settings, "collector")
    log_connect = mq.on_connect_logger("collector")

    def on_connect(c, userdata, flags, reason_code, properties):
        log_connect(c, userdata, flags, reason_code, properties)
        if not reason_code.is_failure:
            c.subscribe(settings.mqtt.topic_telemetry)
            log.info("Enregistrement « %s » dans %s%s", label, path,
                     f" pendant {minutes:g} min" if minutes else " (Ctrl+C pour arrêter)")

    def on_message(c, userdata, msg):
        try:
            data = json.loads(msg.payload)
        except (json.JSONDecodeError, UnicodeDecodeError):
            data = None
        r = (parse_reading(data, settings.device_id, device_from_topic(msg.topic))
             if isinstance(data, dict) else None)
        if r is None:
            state["skipped"] += 1
            log.warning("Mesure invalide ignorée : %.80s", msg.payload)
            return
        row = {"time": datetime.now().isoformat(timespec="seconds"), "device_id": r.device_id,
               "temp": r.temp, "hum": r.hum, "gas": int(r.gas), "motion": r.motion, "label": label}
        writer.writerow(row)
        fh.flush()
        state["count"] += 1
        log.info("[%4d] T=%.1f H=%.1f Gaz=%d Mvt=%d (%s)", state["count"], r.temp, r.hum,
                 r.gas, r.motion, label)
        if deadline and time.time() >= deadline:
            c.disconnect()

    client.on_connect = on_connect
    client.on_message = on_message
    mq.connect(client, settings)
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        pass
    finally:
        fh.close()
        log.info("%d mesures enregistrées (%d invalides ignorées) → %s",
                 state["count"], state["skipped"], path)
    return state["count"]
