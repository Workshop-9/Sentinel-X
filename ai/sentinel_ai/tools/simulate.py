"""Simulateur de boîtier : rejoue de vraies mesures normales et injecte une panne.

* ``--offline`` : tout se passe sur ce PC (aucun réseau) -> démo de l'IA sans matériel ;
* sinon publie sur sentinel/<device>/telemetry comme un vrai ESP (test du dashboard et
  du service anomalies de bout en bout). Boîtier virtuel par défaut : SX-SIM.
"""
from __future__ import annotations

import json
import logging
import time

import pandas as pd

from ..config import Settings
from ..data.dataset import load_dataset
from ..data.scenarios import PERIOD_S, SCENARIOS, inject

log = logging.getLogger(__name__)


def build_stream(settings: Settings, scenario: str | None, at_s: float, duration_s: float) -> pd.DataFrame:
    ds = load_dataset(settings.paths.data_dir)
    normal = ds.raw[ds.raw["label"] == "normal"].reset_index(drop=True)
    n = int(duration_s / PERIOD_S)
    reps = n // len(normal) + 1
    stream = pd.concat([normal] * reps, ignore_index=True).iloc[:n].copy()
    if scenario:
        stream = inject(stream, int(at_s / PERIOD_S), SCENARIOS[scenario])
    return stream


def run(settings: Settings, scenario: str | None = "fuite_gaz", at_s: float = 60,
        duration_s: float = 300, device: str = "SX-SIM", offline: bool = False,
        speed: float = 1.0) -> None:
    if scenario and scenario not in SCENARIOS:
        raise ValueError(f"Scénario inconnu : {scenario} (choix : {', '.join(SCENARIOS)})")
    stream = build_stream(settings, scenario, at_s, duration_s)
    title = SCENARIOS[scenario].title if scenario else "aucune panne"
    log.info("Simulation %s : %d mesures, panne « %s » à t=%.0f s, vitesse x%g",
             device, len(stream), title, at_s, speed)

    if offline:
        from ..anomaly.registry import load_production
        from ..anomaly.service import AnomalyService
        service = AnomalyService(settings, load_production(settings.paths.artifacts_dir),
                                 auto_alarm=False)
        handle = lambda topic, payload, t: service.handle(topic, payload, now=t)  # noqa: E731
        client = None
    else:
        from .. import mqtt as mq
        client = mq.create_client(settings, "simulator", device=device)
        mq.connect(client, settings)
        client.loop_start()

    topic = f"sentinel/{device}/telemetry"
    t0 = time.time()
    try:
        for i, row in enumerate(stream.itertuples()):
            t = t0 + i * PERIOD_S
            msg = {"device_id": device, "ts": int(t), "temp": round(row.temp, 1),
                   "hum": round(row.hum, 1), "gas": int(round(row.gas)), "motion": int(row.motion)}
            if scenario and i == int(at_s / PERIOD_S):
                log.warning(">>> Début de la panne simulée : %s", title)
            if client is None:
                handle(topic, json.dumps(msg), t)
            else:
                client.publish(topic, json.dumps(msg))
            if speed > 0:
                time.sleep(PERIOD_S / speed)
    except KeyboardInterrupt:
        pass
    finally:
        if client is not None:
            client.loop_stop()
            client.disconnect()
