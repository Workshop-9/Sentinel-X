from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from sentinel_ai import paths
from sentinel_ai.anomaly.features import FEATURES, OnlineFeatureExtractor
from sentinel_ai.anomaly.models import ModelBundle, fit_envelope, make_pipeline

FEATURE_PARAMS = {"window": 15, "baseline_halflife": 150, "reset_after_s": 600}


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Chaque test écrit dans un dossier temporaire, jamais dans le dépôt."""
    monkeypatch.setenv("SENTINEL_HOME", str(tmp_path / "home"))
    for var in ("SENTINEL_MQTT_USER", "SENTINEL_MQTT_PASS", "SENTINEL_MQTT_HOST",
                "SENTINEL_MQTT_PORT", "SENTINEL_MQTT_TLS", "SENTINEL_STREAM_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    paths.workdir.cache_clear()
    yield tmp_path / "home"
    paths.workdir.cache_clear()


def normal_signal(n: int = 900, seed: int = 0) -> pd.DataFrame:
    """Signal « normal » réaliste : niveaux stables + bruit capteur + glitchs ADC."""
    rng = np.random.default_rng(seed)
    temp = 24.2 + np.round(rng.normal(0, 0.05, n), 1)
    hum = 53.0 + np.cumsum(rng.normal(0, 0.05, n)) * 0.1 + rng.normal(0, 0.15, n)
    gas = np.where(rng.random(n) < 0.08, 42, 50) + rng.integers(-1, 2, n)
    t = pd.date_range("2026-10-07 10:00:00", periods=n, freq="2s")
    return pd.DataFrame({"time": t, "device_id": "SX-001", "temp": temp, "hum": hum,
                         "gas": gas.astype(float), "motion": 1, "label": "normal"})


def features_of(df: pd.DataFrame) -> pd.DataFrame:
    ex = OnlineFeatureExtractor(**FEATURE_PARAMS)
    rows = [ex.update(r.temp, r.hum, r.gas) for r in df.itertuples()]
    return pd.DataFrame([r for r in rows if r is not None])


@pytest.fixture(scope="session")
def bundle() -> ModelBundle:
    feats = features_of(normal_signal())
    train, calib = feats.iloc[:600], feats.iloc[600:]
    pipe = make_pipeline("isolation_forest", n_estimators=60, random_state=0)
    X = train[FEATURES].to_numpy()
    pipe.fit(X)
    calib_scores = pipe.decision_function(calib[FEATURES].to_numpy())
    thr = float(np.quantile(calib_scores, 0.01))
    return ModelBundle(pipeline=pipe, threshold=thr, features=list(FEATURES),
                       feature_params=dict(FEATURE_PARAMS), algorithm="isolation_forest",
                       version="test-model", envelope=fit_envelope(pipe, X, calib_scores - thr))
