"""Scénarios de pannes synthétiques, injectés PAR-DESSUS de vraies mesures normales.

On ne peut pas provoquer une vraie fuite de gaz ou une surchauffe lente en salle :
on ajoute donc une dérive réaliste au signal réel (bruit capteur conservé) pour
mesurer si — et en combien de secondes — l'IA la détecte. Ces scénarios servent à
l'évaluation et à la démo (`simulate`), jamais à l'entraînement.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

PERIOD_S = 2.0   # cadence d'envoi de l'ESP


@dataclass(frozen=True)
class Scenario:
    key: str
    title: str
    description: str
    duration_s: float
    profile: Callable[[np.ndarray], dict[str, np.ndarray]]   # t (0..1) -> décalages

    @property
    def length(self) -> int:
        return int(self.duration_s / PERIOD_S)

    def offsets(self) -> dict[str, np.ndarray]:
        u = np.linspace(0, 1, self.length)
        prof = self.profile(u)
        zero = np.zeros(self.length)
        return {k: prof.get(k, zero) for k in ("temp", "hum", "gas")}


def _ramp(u: np.ndarray, reach: float) -> np.ndarray:
    """Montée linéaire atteignant 1 à la fraction `reach` du scénario, puis plateau."""
    return np.minimum(u / reach, 1.0)


SCENARIOS: dict[str, Scenario] = {s.key: s for s in [
    Scenario("surchauffe_lente", "Surchauffe lente + micro-dérive du gaz",
             "+2 °C en 3 min et +6 points de gaz : reste sous tout seuil fixe "
             "(exemple du cahier des charges)",
             180, lambda u: {"temp": 2.0 * u, "gas": 6.0 * u}),
    Scenario("fuite_gaz", "Fuite de gaz",
             "+120 points ADC en 20 s puis plateau", 180,
             lambda u: {"gas": 120 * _ramp(u, 20 / 180)}),
    Scenario("choc_thermique", "Départ de feu / choc thermique",
             "+5 °C et -5 % d'humidité en 40 s", 180,
             lambda u: {"temp": 5 * _ramp(u, 40 / 180), "hum": -5 * _ramp(u, 40 / 180)}),
    Scenario("infiltration_humidite", "Infiltration d'eau / condensation",
             "+12 % d'humidité en 60 s", 180,
             lambda u: {"hum": 12 * _ramp(u, 60 / 180)}),
]}


def inject(raw: pd.DataFrame, start: int, scenario: Scenario, keep_plateau: bool = True
           ) -> pd.DataFrame:
    """Copie de `raw` (un seul boîtier, ordre chronologique) avec le scénario ajouté
    à partir de la position `start`."""
    out = raw.copy()
    for col in ("temp", "hum", "gas"):
        out[col] = out[col].astype(float)
    off = scenario.offsets()
    end = min(start + scenario.length, len(out))
    pos = out.columns.get_indexer(["temp", "hum", "gas"])
    for j, col in zip(pos, ("temp", "hum", "gas")):
        out.iloc[start:end, j] += off[col][: end - start]
        if keep_plateau and end < len(out):
            out.iloc[end:, j] += off[col][-1]
    out["gas"] = out["gas"].clip(0, 1024)
    out["hum"] = out["hum"].clip(0, 100)
    return out
