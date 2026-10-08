"""Évaluation : fausses alertes, détection réelle, scénarios synthétiques, robustesse.

Toutes les mesures se font sur des données JAMAIS vues à l'entraînement (split test
chronologique) et avec la même logique de confirmation qu'en production.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from ..data.dataset import extract_features
from ..data.scenarios import SCENARIOS, Scenario, inject
from .detector import AnomalyDetector
from .models import ModelBundle, fit_envelope, make_pipeline

log = logging.getLogger(__name__)

# Règle « naïve » à seuils fixes, utilisée UNIQUEMENT comme point de comparaison
# (interdite dans le produit par le cahier des charges).
STATIC_RULE = {"temp": 40.0, "gas": 400.0}
STATIC_RULE_TEXT = "température > 40 °C ou gaz > 400"
SITE_SHIFT = {"temp": 3.0, "hum": -10.0, "gas": 25.0}   # « autre salle »


def static_rule(raw: pd.DataFrame) -> np.ndarray:
    return ((raw["temp"] > STATIC_RULE["temp"]) | (raw["gas"] > STATIC_RULE["gas"])).to_numpy()


def confirm(flags: np.ndarray, consecutive: int) -> np.ndarray:
    """Alarme confirmée quand `consecutive` anomalies se suivent (comme en production)."""
    out = np.zeros(len(flags), dtype=bool)
    streak = 0
    for i, f in enumerate(flags):
        streak = streak + 1 if f else 0
        out[i] = streak >= consecutive
    return out


def episodes(alarms: np.ndarray) -> int:
    if len(alarms) == 0:
        return 0
    return int(alarms[0]) + int(np.sum(alarms[1:] & ~alarms[:-1]))


def first_delay(alarms: np.ndarray, times: pd.Series) -> float | None:
    if not alarms.any():
        return None
    i = int(np.argmax(alarms))
    return float((times.iloc[i] - times.iloc[0]).total_seconds())


@dataclass
class ScenarioRun:
    scenario: Scenario
    start: int
    window: pd.DataFrame            # features pendant le scénario
    raw_window: pd.DataFrame        # mesures brutes pendant le scénario


@dataclass
class EvalContext:
    feature_params: dict[str, float]
    consecutive: int
    train: pd.DataFrame
    calib: pd.DataFrame
    test: pd.DataFrame
    anomaly: pd.DataFrame
    stream: pd.DataFrame                    # mesures normales brutes du boîtier principal
    test_start: int                         # position du début du test dans `stream`
    scenario_runs: list[ScenarioRun] = field(default_factory=list)
    shifted_test: pd.DataFrame | None = None


def build_context(raw: pd.DataFrame, feats: pd.DataFrame, train: pd.DataFrame,
                  calib: pd.DataFrame, test: pd.DataFrame, feature_params: dict[str, float],
                  consecutive: int, n_offsets: int = 5) -> EvalContext:
    anomaly = feats[feats["label"] == "anomalie"]
    device = test["device_id"].value_counts().idxmax()
    stream = raw[(raw["device_id"] == device) & (raw["label"] == "normal")]
    stream = stream.sort_values("time").reset_index(drop=True)
    test_start = int(np.searchsorted(stream["time"].to_numpy(), test["time"].min().to_datetime64()))
    ctx = EvalContext(feature_params, consecutive, train, calib, test, anomaly, stream, test_start)

    # Scénarios injectés à plusieurs instants de la période de test
    for sc in SCENARIOS.values():
        last = len(stream) - sc.length - 1
        if last <= test_start:
            log.warning("Période de test trop courte pour le scénario %s", sc.key)
            continue
        starts = np.linspace(test_start + 10, last, n_offsets).astype(int)
        for s in np.unique(starts):
            mod = inject(stream, int(s), sc)
            f = extract_features(mod, **feature_params)
            pos = slice(int(s), int(s) + sc.length)
            ctx.scenario_runs.append(ScenarioRun(
                sc, int(s), f.loc[f.index.intersection(range(pos.start, pos.stop))],
                mod.iloc[pos]))

    # Robustesse : même période de test, mais dans une « autre salle » (niveaux décalés)
    shifted = stream.copy()
    for col, delta in SITE_SHIFT.items():
        shifted[col] = shifted[col] + delta
    fs = extract_features(shifted, **feature_params)
    ctx.shifted_test = fs[fs.index >= test_start]
    return ctx


def fit_bundle(algorithm: str, features: list[str], ctx: EvalContext, target_fpr: float,
               n_estimators: int = 200, random_state: int = 42, envelope: bool = True) -> ModelBundle:
    X_train = ctx.train[features].to_numpy(dtype=float)
    pipe = make_pipeline(algorithm, n_estimators, random_state)
    pipe.fit(X_train)
    calib_scores = pipe.decision_function(ctx.calib[features].to_numpy(dtype=float))
    threshold = float(np.quantile(calib_scores, target_fpr))
    env = fit_envelope(pipe, X_train, calib_scores - threshold) if envelope else None
    return ModelBundle(pipeline=pipe, threshold=threshold, features=list(features),
                       feature_params=dict(ctx.feature_params), algorithm=algorithm, envelope=env)


def _latency_ms(bundle: ModelBundle, X: pd.DataFrame, n: int = 30) -> float:
    row = X[bundle.features].to_numpy(dtype=float)[:1]
    bundle.score(row)
    t0 = time.perf_counter()
    for _ in range(n):
        bundle.score(row)
    return (time.perf_counter() - t0) / n * 1000


def evaluate_bundle(bundle: ModelBundle, ctx: EvalContext) -> dict[str, Any]:
    k = ctx.consecutive
    s_test = bundle.score(ctx.test)
    flags_test = s_test < 0
    alarms_test = confirm(flags_test, k)
    hours = len(ctx.test) * 2 / 3600
    res: dict[str, Any] = {
        "test_samples": int(len(ctx.test)),
        "test_minutes": round(len(ctx.test) * 2 / 60, 1),
        "test_fpr": float(flags_test.mean()),
        "test_false_alarms": episodes(alarms_test),
        "test_false_alarms_per_hour": episodes(alarms_test) / hours if hours else None,
        "latency_ms": round(_latency_ms(bundle, ctx.test), 2),
    }

    if len(ctx.anomaly):
        s_an = bundle.score(ctx.anomaly)
        al = confirm(s_an < 0, k)
        res.update({
            "anomaly_samples": int(len(ctx.anomaly)),
            "anomaly_recall": float((s_an < 0).mean()),
            "anomaly_first_alarm_s": first_delay(al, ctx.anomaly["time"]),
            "auc": float(roc_auc_score(
                np.r_[np.zeros(len(s_test)), np.ones(len(s_an))], -np.r_[s_test, s_an])),
        })

    per: dict[str, dict[str, Any]] = {}
    for run in ctx.scenario_runs:
        d = per.setdefault(run.scenario.key, {"runs": 0, "detected": 0, "delays": [],
                                              "static_detected": 0, "static_delays": [],
                                              "plateau": []})
        d["runs"] += 1
        flags = bundle.score(run.window) < 0
        d["plateau"].append(float(flags[-30:].mean()))   # alerte maintenue sur les 60 dernières s
        al = confirm(flags, k)
        delay = first_delay(al, run.window["time"])
        if delay is not None:
            d["detected"] += 1
            d["delays"].append(delay)
        st = static_rule(run.raw_window)
        sd = first_delay(st, run.raw_window["time"])
        if sd is not None:
            d["static_detected"] += 1
            d["static_delays"].append(sd)
    for d in per.values():
        d["median_delay_s"] = float(np.median(d["delays"])) if d["delays"] else None
        d["static_median_delay_s"] = float(np.median(d["static_delays"])) if d["static_delays"] else None
        d["plateau_coverage"] = float(np.mean(d.pop("plateau")))
    res["scenarios"] = per
    total = sum(d["runs"] for d in per.values())
    res["scenario_detection_rate"] = (sum(d["detected"] for d in per.values()) / total) if total else None
    res["plateau_coverage"] = (float(np.mean([d["plateau_coverage"] for d in per.values()]))
                               if per else None)

    if ctx.shifted_test is not None and len(ctx.shifted_test):
        res["site_shift_fpr"] = float((bundle.score(ctx.shifted_test) < 0).mean())
    return res


def explain_matrix(bundle: ModelBundle, ctx: EvalContext) -> pd.DataFrame:
    """|z-score| moyen de chaque feature au moment de la détection, par scénario :
    montre QUELLE dynamique a fait réagir le modèle."""
    rows: dict[str, list[np.ndarray]] = {}
    for run in ctx.scenario_runs:
        al = confirm(bundle.score(run.window) < 0, ctx.consecutive)
        if al.any():
            x = run.window[bundle.features].to_numpy(dtype=float)[int(np.argmax(al))]
            rows.setdefault(run.scenario.title, []).append(np.abs(bundle.zscores(x)[0]))
    if len(ctx.anomaly):
        al = confirm(bundle.score(ctx.anomaly) < 0, ctx.consecutive)
        if al.any():
            x = ctx.anomaly[bundle.features].to_numpy(dtype=float)[int(np.argmax(al))]
            rows["Session anomalie réelle"] = [np.abs(bundle.zscores(x)[0])]
    return pd.DataFrame({k: np.mean(v, axis=0) for k, v in rows.items()},
                        index=bundle.features).T


def run_detector(bundle: ModelBundle, raw: pd.DataFrame, consecutive: int, max_freeze: int,
                 warm_until: int = 0) -> pd.DataFrame:
    """Rejoue `raw` dans le détecteur de production (avec gel de la ligne de base).
    Les `warm_until` premières mesures ne servent qu'à amorcer l'état (pas de scoring)."""
    det = AnomalyDetector(bundle, consecutive, max_freeze)
    t = (raw["time"] - pd.Timestamp(0)).dt.total_seconds().to_numpy()
    rows = []
    for i, (tt, temp, hum, gas) in enumerate(zip(t, raw["temp"], raw["hum"], raw["gas"])):
        if i < warm_until:
            det.extractor.update(temp, hum, gas, t=float(tt), adapt=True)
            continue
        d = det.step(temp, hum, gas, t=float(tt))
        rows.append({"time": raw["time"].iloc[i], "temp": temp, "hum": hum, "gas": gas,
                     "score": d.score if d else np.nan,
                     "level": d.level if d else "warmup",
                     "alarm_triggered": bool(d and d.alarm_triggered),
                     "causes": "; ".join(c["label"] for c in d.causes) if d else ""})
    return pd.DataFrame(rows)


@dataclass
class RecoveryResult:
    seconds: dict[str, float | None]        # délai de retour à la normale par variante
    traces: dict[str, pd.DataFrame]         # sorties du détecteur pour les graphiques
    pulse_start: pd.Timestamp
    pulse_end: pd.Timestamp


def recovery_test(bundle: ModelBundle, ctx: EvalContext, max_freeze: int) -> RecoveryResult:
    """Fuite de gaz de 60 s puis retour à la normale : combien de temps pour revenir
    à « normal » ? Comparaison avec / sans gel de la ligne de base."""
    pulse = Scenario("pulse_gaz", "Bouffée de gaz (60 s)", "+120 en 20 s, 60 s, puis arrêt", 60,
                     lambda u: {"gas": 120 * np.minimum(u * 3, 1.0)})
    start = ctx.test_start + 20
    mod = inject(ctx.stream, start, pulse, keep_plateau=False)
    end_time = mod["time"].iloc[start + pulse.length]
    seconds: dict[str, float | None] = {}
    traces: dict[str, pd.DataFrame] = {}
    for name, freeze in (("avec_gel", max_freeze), ("sans_gel", 0)):
        df = run_detector(bundle, mod.iloc[: start + pulse.length + 400], ctx.consecutive,
                          freeze, warm_until=max(0, start - 30))
        after = df[df["time"] >= end_time].reset_index(drop=True)
        calm = (after["level"] == "normal").to_numpy()
        # retour à la normale = 5 mesures normales d'affilée (10 s)
        stable = [i for i in range(len(calm) - 4) if calm[i:i + 5].all()]
        seconds[name] = (float((after["time"].iloc[stable[0]] - end_time).total_seconds())
                         if stable else None)
        traces[name] = df
    return RecoveryResult(seconds, traces, mod["time"].iloc[start], end_time)
