"""Contrat des messages de télémétrie et plages physiques des capteurs."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

# Plages physiquement possibles (fiches techniques) : au-delà, la mesure est invalide
# (capteur débranché, erreur de lecture), ce n'est PAS une anomalie à détecter.
SENSOR_RANGES = {
    "temp": (-40.0, 80.0),    # DHT22, °C
    "hum": (0.0, 100.0),      # DHT22, %
    "gas": (0.0, 1024.0),     # MQ-2 sur l'ADC de l'ESP8266 (valeur brute, pas des ppm)
}
CSV_COLUMNS = ["time", "device_id", "temp", "hum", "gas", "motion", "label"]


@dataclass(frozen=True)
class Reading:
    device_id: str
    temp: float
    hum: float
    gas: float
    motion: int = 0

    def values(self) -> tuple[float, float, float]:
        return self.temp, self.hum, self.gas


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def parse_reading(payload: dict[str, Any], default_device: str = "SX-001",
                  topic_device: str | None = None) -> Reading | None:
    """Message JSON de l'ESP -> Reading, ou None si une mesure manque ou est hors plage.

    L'identité du boîtier vient en priorité du topic (protégé par les ACL du broker) :
    un champ device_id falsifié dans le JSON ne peut pas usurper un autre boîtier."""
    if not isinstance(payload, dict):
        return None
    values = {}
    for key, (lo, hi) in SENSOR_RANGES.items():
        x = _number(payload.get(key))
        if x is None or not lo <= x <= hi:
            return None
        values[key] = x
    motion = _number(payload.get("motion"))
    device = topic_device or payload.get("device_id") or default_device
    return Reading(device_id=str(device), motion=int(motion or 0), **values)


def device_from_topic(topic: str) -> str | None:
    """sentinel/<device>/telemetry -> <device>"""
    parts = topic.split("/")
    return parts[1] if len(parts) >= 3 and parts[1] else None
