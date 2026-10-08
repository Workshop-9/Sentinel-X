"""Extraction de caractéristiques *en flux* (une mesure à la fois).

Le même code sert à l'entraînement et en production : aucune divergence possible
entre les features vues par le modèle à l'entraînement et en direct.

Idée clé : le modèle n'apprend pas des *niveaux* (24 °C, gaz = 50) qui changent
d'une salle à l'autre, mais des *dynamiques* :

* ``*_dev``  écart à une ligne de base adaptative (moyenne mobile exponentielle,
  demi-vie 5 min) -> « plus chaud que d'habitude ICI » ;
* ``d_*``    variation sur 30 s -> vitesse de montée/descente ;
* ``gas_std`` instabilité du gaz sur 30 s -> micro-fluctuations.
"""
from __future__ import annotations

from collections import deque

import numpy as np

SENSORS = ("temp", "hum", "gas")

# Features du modèle de production
FEATURES = ["temp_dev", "hum_dev", "gas_dev", "d_temp", "d_hum", "d_gas", "gas_std"]
# Ancienne version (niveaux absolus) : gardée pour la comparaison dans le rapport
LEGACY_FEATURES = ["temp", "hum", "gas", "d_temp", "d_hum", "d_gas", "gas_std"]
ALL_FEATURES = list(dict.fromkeys(
    FEATURES + LEGACY_FEATURES + ["temp_std", "hum_std"]))

LABELS_FR = {
    "temp_dev": ("température au-dessus de la normale", "température sous la normale"),
    "hum_dev": ("humidité au-dessus de la normale", "humidité sous la normale"),
    "gas_dev": ("gaz au-dessus de la normale", "gaz sous la normale"),
    "d_temp": ("température en hausse rapide", "température en baisse rapide"),
    "d_hum": ("humidité en hausse rapide", "humidité en baisse rapide"),
    "d_gas": ("gaz en hausse rapide", "gaz en baisse rapide"),
    "gas_std": ("gaz instable", "gaz anormalement stable"),
    "temp_std": ("température instable", "température anormalement stable"),
    "hum_std": ("humidité instable", "humidité anormalement stable"),
    "temp": ("température élevée", "température basse"),
    "hum": ("humidité élevée", "humidité basse"),
    "gas": ("gaz élevé", "gaz bas"),
}


def describe(feature: str, z: float) -> str:
    up, down = LABELS_FR.get(feature, (feature, feature))
    return up if z >= 0 else down


class OnlineFeatureExtractor:
    """État glissant d'un boîtier. `update()` renvoie un dict de features, ou None
    tant que la fenêtre n'est pas pleine (30 premières secondes)."""

    def __init__(self, window: int = 15, baseline_halflife: float = 150,
                 reset_after_s: float = 600):
        self.window = int(window)
        self.alpha = 1.0 - 0.5 ** (1.0 / float(baseline_halflife))
        self.reset_after_s = float(reset_after_s)
        self.reset()

    def reset(self) -> None:
        self.buffer: deque[np.ndarray] = deque(maxlen=self.window + 1)
        self.baseline: np.ndarray | None = None
        self.n_adapt = 0
        self.last_t: float | None = None

    @property
    def ready(self) -> bool:
        return len(self.buffer) == self.buffer.maxlen

    def adapt(self, x: np.ndarray) -> None:
        """Fait évoluer la ligne de base vers x (moyenne cumulée au démarrage, puis EWMA)."""
        self.n_adapt += 1
        a = max(self.alpha, 1.0 / self.n_adapt)
        self.baseline = self.baseline + a * (x - self.baseline)

    def update(self, temp: float, hum: float, gas: float, t: float | None = None,
               adapt: bool = True) -> dict[str, float] | None:
        """Ajoute une mesure. `t` = horodatage en secondes (détection des coupures).
        Avec adapt=False, l'appelant décide ensuite d'appeler `adapt()` (gel en anomalie)."""
        if t is not None and self.last_t is not None and t - self.last_t > self.reset_after_s:
            self.reset()
        if t is not None:
            self.last_t = t

        x = np.array([temp, hum, gas], dtype=float)
        if self.baseline is None:
            self.baseline = x.copy()
        dev = x - self.baseline
        self.buffer.append(x)
        if adapt:
            self.adapt(x)
        if not self.ready:
            return None

        win = np.asarray(self.buffer)
        delta = win[-1] - win[0]             # variation sur `window` mesures
        recent = win[1:]                     # les `window` dernières mesures
        std = recent.std(axis=0, ddof=1)
        return {
            "temp": x[0], "hum": x[1], "gas": x[2],
            "temp_dev": dev[0], "hum_dev": dev[1], "gas_dev": dev[2],
            "d_temp": delta[0], "d_hum": delta[1], "d_gas": delta[2],
            "temp_std": std[0], "hum_std": std[1], "gas_std": std[2],
        }
