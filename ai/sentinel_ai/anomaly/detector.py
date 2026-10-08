"""Détecteur en ligne pour UN boîtier : features -> score -> confirmation -> décision."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .features import OnlineFeatureExtractor
from .models import ModelBundle

NORMAL, SUSPECT, ALARM = "normal", "suspect", "alarm"


@dataclass
class Decision:
    score: float
    is_anomaly: bool
    streak: int
    level: str                       # normal | suspect | alarm
    alarm_triggered: bool            # True uniquement à l'instant où l'alarme est confirmée
    causes: list[dict[str, Any]] = field(default_factory=list)
    features: dict[str, float] = field(default_factory=dict)


class AnomalyDetector:
    """
    * ``consecutive`` : nb d'anomalies d'affilée pour confirmer (anti fausses alertes) ;
    * gel de la ligne de base pendant une anomalie : une fuite de gaz ne « devient » pas
      la nouvelle normale. Au-delà de ``max_freeze`` mesures, on ré-apprend le nouveau
      niveau (ex. boîtier déplacé dans une autre salle).
    """

    def __init__(self, bundle: ModelBundle, consecutive: int = 3, max_freeze: int = 150):
        self.bundle = bundle
        self.consecutive = int(consecutive)
        self.max_freeze = int(max_freeze)
        p = bundle.feature_params
        self.extractor = OnlineFeatureExtractor(
            window=p["window"], baseline_halflife=p["baseline_halflife"],
            reset_after_s=p["reset_after_s"])
        self.streak = 0
        self.frozen = 0

    @property
    def warming_up(self) -> bool:
        return not self.extractor.ready

    def step(self, temp: float, hum: float, gas: float, t: float | None = None) -> Decision | None:
        feats = self.extractor.update(temp, hum, gas, t=t, adapt=False)
        x = np.array([temp, hum, gas], dtype=float)
        if feats is None:                      # fenêtre pas encore pleine
            self.extractor.adapt(x)
            self.streak = 0
            return None

        row = np.array([[feats[f] for f in self.bundle.features]])
        score = float(self.bundle.score(row)[0])
        is_anomaly = score < 0

        if is_anomaly and self.frozen < self.max_freeze:
            self.frozen += 1                   # ligne de base gelée
        else:
            self.extractor.adapt(x)
            if not is_anomaly:
                self.frozen = 0

        self.streak = self.streak + 1 if is_anomaly else 0
        confirmed = self.streak >= self.consecutive
        level = ALARM if confirmed else SUSPECT if is_anomaly else NORMAL
        return Decision(
            score=score, is_anomaly=is_anomaly, streak=self.streak, level=level,
            alarm_triggered=self.streak == self.consecutive,
            causes=self.bundle.explain(row) if is_anomaly else [],
            features={k: round(float(v), 3) for k, v in feats.items()},
        )
