"""Chargement du jeu de données : CSV collectés + annotations manuelles + contrôles qualité."""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from ..anomaly.features import OnlineFeatureExtractor
from ..paths import read_locations
from .schema import CSV_COLUMNS, SENSOR_RANGES

log = logging.getLogger(__name__)

ANNOTATIONS_FILE = "annotations.csv"


@dataclass
class Dataset:
    raw: pd.DataFrame                       # mesures valides, triées, étiquetées
    report: dict[str, Any] = field(default_factory=dict)

    def label_counts(self) -> dict[str, int]:
        return self.raw["label"].value_counts().to_dict()


def find_csv_files(data_dir: str) -> list[Path]:
    files: list[Path] = []
    for d in read_locations(data_dir):
        if d.is_dir():
            files += sorted(p for p in d.glob("telemetry*.csv"))
    return files


def find_annotations(data_dir: str) -> Path | None:
    for d in read_locations(data_dir):
        if (d / ANNOTATIONS_FILE).exists():
            return d / ANNOTATIONS_FILE
    return None


def _fingerprint(frames: list[pd.DataFrame]) -> str:
    h = hashlib.sha256()
    for f in frames:
        h.update(pd.util.hash_pandas_object(f, index=False).values.tobytes())
    return h.hexdigest()[:16]


def apply_annotations(df: pd.DataFrame, path: Path | None) -> tuple[pd.DataFrame, list[dict]]:
    """Ré-étiquette des plages horaires (ex. manipulation du boîtier entre deux sessions)."""
    applied: list[dict] = []
    if path is None:
        return df, applied
    ann = pd.read_csv(path, comment="#", parse_dates=["start", "end"], dtype={"device_id": str})
    for a in ann.itertuples():
        mask = (df["time"] >= a.start) & (df["time"] <= a.end)
        if isinstance(a.device_id, str) and a.device_id not in ("", "*"):
            mask &= df["device_id"] == a.device_id
        n = int(mask.sum())
        df.loc[mask, "label"] = a.label
        applied.append({"start": str(a.start), "end": str(a.end), "label": a.label,
                        "rows": n, "reason": a.reason})
    return df, applied


def load_dataset(data_dir: str = "data") -> Dataset:
    files = find_csv_files(data_dir)
    if not files:
        raise FileNotFoundError(
            "Aucun fichier data/telemetry*.csv : lance d'abord « python -m sentinel_ai collect normal »")

    frames = [pd.read_csv(p) for p in files]
    df = pd.concat(frames, ignore_index=True)
    missing = set(CSV_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"Colonnes manquantes dans les CSV : {sorted(missing)}")
    rows_read = len(df)

    df = df.drop_duplicates()
    duplicates = rows_read - len(df)

    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    df["device_id"] = df["device_id"].fillna("SX-001").astype(str)
    valid = df["time"].notna()
    for col, (lo, hi) in SENSOR_RANGES.items():
        df[col] = pd.to_numeric(df[col], errors="coerce")
        valid &= df[col].between(lo, hi)
    invalid = int((~valid).sum())
    df = df[valid].copy()
    df["motion"] = pd.to_numeric(df["motion"], errors="coerce").fillna(0).astype(int)
    df["label"] = df["label"].fillna("normal").astype(str)
    df = df.sort_values(["device_id", "time"], kind="stable").reset_index(drop=True)

    ann_path = find_annotations(data_dir)
    df, applied = apply_annotations(df, ann_path)

    report = {
        "files": [p.name for p in files],         # pas de chemin local dans les artefacts
        "rows_read": rows_read,
        "duplicates_removed": duplicates,
        "invalid_removed": invalid,
        "rows": len(df),
        "devices": sorted(df["device_id"].unique().tolist()),
        "start": str(df["time"].min()),
        "end": str(df["time"].max()),
        "labels": df["label"].value_counts().to_dict(),
        "annotations": applied,
        "fingerprint": _fingerprint(frames),
    }
    log.info("Données : %d mesures valides (%s) — %d doublons, %d invalides retirés",
             len(df), report["labels"], duplicates, invalid)
    return Dataset(raw=df, report=report)


def extract_features(raw: pd.DataFrame, window: int, baseline_halflife: float,
                     reset_after_s: float) -> pd.DataFrame:
    """Rejoue chaque boîtier dans l'ordre chronologique avec l'extracteur EN FLUX
    (identique à la production). Renvoie une ligne par mesure ayant des features."""
    out = []
    for device, g in raw.groupby("device_id", sort=False):
        ex = OnlineFeatureExtractor(window, baseline_halflife, reset_after_s)
        t = (g["time"] - pd.Timestamp(0)).dt.total_seconds().to_numpy()
        for i, (tt, temp, hum, gas) in enumerate(zip(t, g["temp"], g["hum"], g["gas"])):
            f = ex.update(temp, hum, gas, t=float(tt))
            if f is not None:
                f["row"] = g.index[i]
                out.append(f)
    feats = pd.DataFrame(out).set_index("row")
    feats.index.name = None
    return raw[["time", "device_id", "label"]].join(feats, how="inner")


def chronological_split(df: pd.DataFrame, train_frac: float, calib_frac: float
                        ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Découpage dans le temps (jamais aléatoire sur une série temporelle)."""
    df = df.sort_values("time", kind="stable")
    n = len(df)
    a, b = int(n * train_frac), int(n * (train_frac + calib_frac))
    return df.iloc[:a], df.iloc[a:b], df.iloc[b:]
