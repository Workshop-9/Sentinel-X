"""Modèles candidats (non supervisés : appris sur le fonctionnement normal uniquement)
et « bundle » sérialisé = pipeline + seuil calibré + paramètres des features."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from sklearn.covariance import EllipticEnvelope
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM

from .features import describe

ALGORITHMS = {
    "isolation_forest": "Isolation Forest",
    "lof": "Local Outlier Factor",
    "ocsvm": "One-Class SVM",
    "robust_covariance": "Covariance robuste (MCD)",
}


def make_pipeline(algorithm: str, n_estimators: int = 200, random_state: int = 42) -> Pipeline:
    if algorithm == "isolation_forest":
        est = IsolationForest(n_estimators=n_estimators, random_state=random_state)
    elif algorithm == "lof":
        est = LocalOutlierFactor(n_neighbors=35, novelty=True)
    elif algorithm == "ocsvm":
        est = OneClassSVM(nu=0.01, gamma="scale")
    elif algorithm == "robust_covariance":
        est = EllipticEnvelope(support_fraction=0.9, random_state=random_state)
    else:
        raise ValueError(f"Algorithme inconnu : {algorithm} (choix : {', '.join(ALGORITHMS)})")
    return Pipeline([("scaler", StandardScaler()), ("model", est)])


def fit_envelope(pipeline: Pipeline, X_train: np.ndarray, calib_scores: np.ndarray,
                 margin: float = 1.5, floor: float = 6.0) -> dict[str, float]:
    """Enveloppe statistique APPRISE sur les données normales.

    Les modèles à base d'arbres (Isolation Forest) saturent hors du domaine
    d'entraînement : un écart de +100 écarts-types sur une seule feature n'est pas
    mieux isolé qu'un point de bordure. L'enveloppe borne chaque feature à
    `margin` x le plus grand écart observé en fonctionnement normal (quantile 99,9 %,
    au moins `floor` écarts-types). Ce n'est pas un seuil capteur fixe : la borne
    est apprise et porte sur des dynamiques relatives (écarts, variations).
    """
    scaler: StandardScaler = pipeline.named_steps["scaler"]
    z = np.abs((X_train - scaler.mean_) / scaler.scale_).max(axis=1)
    return {
        "z_max": float(max(floor, margin * np.quantile(z, 0.999))),
        "score_scale": float(max(np.std(calib_scores), 1e-6)),
    }


@dataclass
class ModelBundle:
    """Tout ce qu'il faut pour scorer en production, dans un seul fichier."""
    pipeline: Pipeline
    threshold: float
    features: list[str]
    feature_params: dict[str, float]
    algorithm: str
    version: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    envelope: dict[str, float] | None = None

    def score(self, X: pd.DataFrame | np.ndarray) -> np.ndarray:
        """Score d'anomalie : < 0 = anormal (même convention que l'ancien modèle).
        = min(score du modèle, score de l'enveloppe) : anormal si l'un OU l'autre l'est."""
        if isinstance(X, pd.DataFrame):
            X = X[self.features]
        X = np.atleast_2d(np.asarray(X, dtype=float))
        s = self.pipeline.decision_function(X) - self.threshold
        if self.envelope:
            # < 0 dès qu'une feature sort de l'enveloppe ; échelle log pour rester comparable
            # aux scores du modèle (pas de valeurs extrêmes qui écrasent les graphiques)
            zmax = np.maximum(np.abs(self.zscores(X)).max(axis=1), 1e-9)
            s_env = self.envelope["score_scale"] * np.log(self.envelope["z_max"] / zmax)
            s = np.minimum(s, s_env)
        return s

    def zscores(self, X: np.ndarray) -> np.ndarray:
        scaler: StandardScaler = self.pipeline.named_steps["scaler"]
        return (np.atleast_2d(X) - scaler.mean_) / scaler.scale_

    def explain(self, x: np.ndarray, top: int = 2, min_z: float = 3.0) -> list[dict[str, Any]]:
        """Causes probables : features les plus éloignées de leur valeur normale (en écarts-types)."""
        z = self.zscores(x)[0]
        order = np.argsort(-np.abs(z))[:top]
        return [
            {"feature": self.features[i], "z": round(float(z[i]), 1),
             "label": describe(self.features[i], float(z[i]))}
            for i in order if abs(z[i]) >= min_z
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": 2, "pipeline": self.pipeline, "threshold": self.threshold,
            "features": self.features, "feature_params": self.feature_params,
            "algorithm": self.algorithm, "version": self.version, "metadata": self.metadata,
            "envelope": self.envelope,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ModelBundle":
        if d.get("format") != 2:
            raise ValueError("Format de modèle non reconnu (ré-entraîner : python -m sentinel_ai train)")
        return cls(pipeline=d["pipeline"], threshold=d["threshold"], features=d["features"],
                   feature_params=d["feature_params"], algorithm=d["algorithm"],
                   version=d.get("version", ""), metadata=d.get("metadata", {}),
                   envelope=d.get("envelope"))
