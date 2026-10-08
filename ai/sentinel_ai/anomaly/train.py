"""Pipeline d'entraînement complet de la maintenance prédictive.

données -> contrôles qualité -> features en flux -> split chronologique
-> benchmark de 4 algorithmes -> calibration du seuil -> évaluation (test, anomalie
réelle, scénarios, robustesse, retour à la normale) -> contrôles qualité (gates)
-> modèle versionné + rapport + model card.
"""
from __future__ import annotations

import json
import logging
import platform
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import sklearn

from .. import __version__
from ..config import Settings
from ..data.dataset import chronological_split, extract_features, load_dataset
from .evaluate import (STATIC_RULE_TEXT, build_context, evaluate_bundle, explain_matrix,
                       fit_bundle, recovery_test, run_detector)
from .features import FEATURES, LEGACY_FEATURES
from .models import ALGORITHMS
from .registry import Registry

log = logging.getLogger(__name__)

MIN_NORMAL_SAMPLES = 200      # ≈ 7 minutes de fonctionnement normal


@dataclass
class TrainResult:
    version: str
    directory: Path
    promoted: bool
    gates_passed: bool
    metrics: dict[str, Any]


def check_gates(m: dict[str, Any], settings: Settings) -> list[dict[str, Any]]:
    g = settings.anomaly.gates
    checks = [
        ("Alarmes à tort / heure (test)", m["test_false_alarms_per_hour"], "<=",
         g.max_false_alarms_per_hour),
        ("Mesures suspectes (test)", m["test_fpr"], "<=", g.max_test_fpr),
    ]
    if m.get("anomaly_recall") is not None:
        checks.append(("Détection anomalie réelle", m["anomaly_recall"], ">=", g.min_anomaly_recall))
    if m.get("scenario_detection_rate") is not None:
        checks.append(("Scénarios détectés", m["scenario_detection_rate"], ">=",
                       g.min_scenarios_detected))
        checks.append(("Alerte maintenue (incident)", m["plateau_coverage"], ">=",
                       g.min_plateau_coverage))
    return [{"name": n, "value": v, "op": op, "limit": lim,
             "passed": bool(v <= lim if op == "<=" else v >= lim)} for n, v, op, lim in checks]


def _flat(algo: str, m: dict[str, Any]) -> dict[str, Any]:
    sc = m.get("scenarios", {})
    delays = [d["median_delay_s"] for d in sc.values() if d["median_delay_s"] is not None]
    return {
        "algorithm": algo, "name": ALGORITHMS[algo],
        "test_fpr": m["test_fpr"], "false_alarms_per_hour": m["test_false_alarms_per_hour"],
        "anomaly_recall": m.get("anomaly_recall"), "auc": m.get("auc"),
        "scenario_detection_rate": m.get("scenario_detection_rate"),
        "mean_scenario_delay_s": float(np.mean(delays)) if delays else None,
        "slow_overheat_delay_s": sc.get("surchauffe_lente", {}).get("median_delay_s"),
        "plateau_coverage": m.get("plateau_coverage"),
        "latency_ms": m["latency_ms"],
    }


def _json_default(o: Any) -> Any:
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (pd.Timestamp,)):
        return o.isoformat()
    raise TypeError(type(o))


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=_json_default),
                    encoding="utf-8")


def train(settings: Settings, promote: bool = True, make_report: bool = True) -> TrainResult:
    a = settings.anomaly
    fparams = asdict(a.features)

    # 1. Données
    ds = load_dataset(settings.paths.data_dir)
    feats = extract_features(ds.raw, **fparams)
    normal = feats[feats["label"] == "normal"]
    if len(normal) < MIN_NORMAL_SAMPLES:
        raise ValueError(f"Seulement {len(normal)} mesures normales exploitables : il en faut "
                         f"au moins {MIN_NORMAL_SAMPLES} (≈ 7 min de collecte)")
    tr, ca, te = chronological_split(normal, a.training.train_frac, a.training.calib_frac)
    log.info("Split chronologique : train %d | calibration %d | test %d", len(tr), len(ca), len(te))

    # 2. Contexte d'évaluation (scénarios injectés, salle décalée)
    ctx = build_context(ds.raw, feats, tr, ca, te, fparams, a.live.consecutive)

    # 3. Benchmark des algorithmes (mêmes données, même protocole)
    algos = list(dict.fromkeys(a.training.benchmark + [a.model.algorithm]))
    bundles, metrics = {}, {}
    for algo in algos:
        b = fit_bundle(algo, FEATURES, ctx, a.training.target_fpr,
                       a.model.n_estimators, a.model.random_state)
        bundles[algo], metrics[algo] = b, evaluate_bundle(b, ctx)
        log.info("  %-18s FPR test %.1f %% | scénarios %.0f %% | %.2f ms", algo,
                 100 * metrics[algo]["test_fpr"],
                 100 * (metrics[algo]["scenario_detection_rate"] or 0), metrics[algo]["latency_ms"])
    benchmark = pd.DataFrame([_flat(k, metrics[k]) for k in algos])

    prod = bundles[a.model.algorithm]
    m = metrics[a.model.algorithm]

    # 4. Ablations : features « niveaux absolus » (ancienne version), modèle sans enveloppe
    legacy = fit_bundle(a.model.algorithm, LEGACY_FEATURES, ctx, a.training.target_fpr,
                        a.model.n_estimators, a.model.random_state)
    m_legacy = evaluate_bundle(legacy, ctx)
    bare = fit_bundle(a.model.algorithm, FEATURES, ctx, a.training.target_fpr,
                      a.model.n_estimators, a.model.random_state, envelope=False)
    m_bare = evaluate_bundle(bare, ctx)

    # 5. Comportement en production : retour à la normale, chronologie de l'anomalie réelle
    recovery = recovery_test(prod, ctx, a.live.max_freeze)
    timeline = _real_anomaly_timeline(prod, ds.raw, settings)
    explain = explain_matrix(prod, ctx)

    # 6. Contrôles qualité avant mise en production
    gates = check_gates(m, settings)
    passed = all(g["passed"] for g in gates)

    # 7. Sauvegarde versionnée
    reg = Registry.for_writing(settings.paths.artifacts_dir)
    version, vdir = reg.new_version(a.model.algorithm)
    prod.version = version
    prod.metadata = {
        "trained_at": pd.Timestamp.now().isoformat(timespec="seconds"),
        "sentinel_ai": __version__, "sklearn": sklearn.__version__,
        "python": platform.python_version(),
        "data_fingerprint": ds.report["fingerprint"],
        "train_period": [str(tr["time"].min()), str(tr["time"].max())],
        "target_fpr": a.training.target_fpr,
    }
    summary = {
        "test_fpr": m["test_fpr"], "anomaly_recall": m.get("anomaly_recall"),
        "scenario_detection_rate": m.get("scenario_detection_rate"), "gates_passed": passed,
    }
    digest = reg.save(prod, vdir, summary, promote=promote and passed)

    splits = {name: {"rows": len(d), "start": str(d["time"].min()), "end": str(d["time"].max())}
              for name, d in (("train", tr), ("calibration", ca), ("test", te))}
    full = {
        "version": version, "algorithm": a.model.algorithm, "sha256": digest,
        "promoted": promote and passed, "features": FEATURES, "feature_params": fparams,
        "threshold": prod.threshold, "envelope": prod.envelope, "target_fpr": a.training.target_fpr,
        "consecutive": a.live.consecutive, "splits": splits, "metrics": m,
        "legacy_metrics": m_legacy, "no_envelope_metrics": m_bare,
        "recovery_s": recovery.seconds, "gates": gates,
        "static_rule": STATIC_RULE_TEXT, "metadata": prod.metadata,
    }
    write_json(vdir / "metrics.json", full)
    write_json(vdir / "data_profile.json", ds.report)
    benchmark.to_csv(vdir / "benchmark.csv", index=False)
    timeline.to_csv(vdir / "real_anomaly_timeline.csv", index=False)

    if make_report:
        try:
            from .report import build_report
            build_report(vdir, full, ds, ctx, benchmark, explain, timeline, recovery, prod)
        except Exception:  # le modèle reste valide même si un graphique échoue
            log.exception("Échec de génération du rapport (le modèle est bien sauvegardé)")

    _log_summary(full, vdir, passed, promote)
    return TrainResult(version, vdir, promote and passed, passed, full)


def _real_anomaly_timeline(bundle, raw: pd.DataFrame, settings: Settings) -> pd.DataFrame:
    """Rejoue la fin de session normale + la session anomalie dans le détecteur réel."""
    an = raw[raw["label"] == "anomalie"]
    if an.empty:
        return pd.DataFrame()
    device = an["device_id"].iloc[0]
    stream = raw[raw["device_id"] == device].sort_values("time").reset_index(drop=True)
    first = int(stream.index[stream["label"] == "anomalie"][0])
    last = int(stream.index[stream["label"] == "anomalie"][-1])
    start = max(0, first - 150)                     # 5 min de contexte
    out = run_detector(bundle, stream.iloc[: last + 1], settings.anomaly.live.consecutive,
                       settings.anomaly.live.max_freeze, warm_until=start)
    out["label"] = stream["label"].iloc[start: last + 1].to_numpy()
    return out


def _log_summary(r: dict[str, Any], vdir: Path, passed: bool, promote: bool) -> None:
    m = r["metrics"]
    log.info("─" * 60)
    log.info("Modèle %s", r["version"])
    log.info("  Test (%s min jamais vues) : %d alarme(s) confirmée(s) à tort, %.1f %% de mesures "
             "isolées suspectes", m["test_minutes"], m["test_false_alarms"], 100 * m["test_fpr"])
    if m.get("anomaly_recall") is not None:
        log.info("  Session anomalie réelle : %.0f %% détecté, AUC %.3f",
                 100 * m["anomaly_recall"], m["auc"])
    for key, d in m["scenarios"].items():
        log.info("  Scénario %-22s %d/%d détecté(s), délai médian %s s (règle fixe : %d/%d)",
                 key, d["detected"], d["runs"], d["median_delay_s"], d["static_detected"], d["runs"])
    for g in r["gates"]:
        log.info("  Gate %-28s %.3f %s %.3f  %s", g["name"], g["value"], g["op"], g["limit"],
                 "OK" if g["passed"] else "ÉCHEC")
    if passed and promote:
        log.info("Modèle promu en production. Rapport : %s", vdir / "report.html")
    elif not passed:
        log.warning("Contrôles qualité non validés : le modèle en production n'est PAS remplacé")
    else:
        log.info("Modèle enregistré sans promotion (--no-promote)")
