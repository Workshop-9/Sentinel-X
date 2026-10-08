"""Benchmark de latence de la vision (exigence du sujet : < 100 ms par image en 640x480)."""
from __future__ import annotations

import json
import logging
import platform
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from ..config import Settings
from ..paths import resolve, workdir
from .detector import PersonDetector

log = logging.getLogger(__name__)
BUDGET_MS = 100.0


def sample_frames(settings: Settings, camera: int | None) -> list[np.ndarray]:
    v = settings.vision
    if camera is not None:
        cap = cv2.VideoCapture(camera, cv2.CAP_DSHOW)
        frames = []
        for _ in range(10):
            ok, f = cap.read()
            if ok:
                frames.append(f)
        cap.release()
        if not frames:
            raise RuntimeError(f"Aucune image reçue de la caméra {camera}")
    else:   # images d'exemple fournies avec ultralytics (aucun fichier ajouté au dépôt)
        import ultralytics
        assets = Path(ultralytics.__file__).parent / "assets"
        frames = [cv2.imread(str(p)) for p in sorted(assets.glob("*.jpg"))]
        frames = [f for f in frames if f is not None]
    return [cv2.resize(f, (v.frame_width, v.frame_height)) for f in frames]


def run(settings: Settings, n: int = 60, camera: int | None = None) -> dict:
    v = settings.vision
    det = PersonDetector(resolve(v.weights), v.conf_min, imgsz=max(v.frame_width, v.frame_height))
    frames = sample_frames(settings, camera)
    for f in frames[:3]:                       # préchauffage (initialisation torch)
        det(f)
    lat, persons = [], []
    for i in range(n):
        d = det(frames[i % len(frames)])
        lat.append(d.inference_ms)
        persons.append(d.persons)
    a = np.array(lat)
    try:
        import torch
        torch_v = torch.__version__
    except ImportError:  # pragma: no cover
        torch_v = "?"
    res = {
        "date": datetime.now().isoformat(timespec="seconds"),
        "model": Path(v.weights).name,
        "resolution": f"{v.frame_width}x{v.frame_height}",
        "source": f"camera {camera}" if camera is not None else "images d'exemple ultralytics",
        "frames": n,
        "mean_ms": round(float(a.mean()), 1),
        "p50_ms": round(float(np.percentile(a, 50)), 1),
        "p95_ms": round(float(np.percentile(a, 95)), 1),
        "max_ms": round(float(a.max()), 1),
        "fps": round(1000.0 / float(a.mean()), 1),
        "budget_ms": BUDGET_MS,
        "within_budget": bool(np.percentile(a, 95) < BUDGET_MS),
        "persons_detected_per_frame": round(float(np.mean(persons)), 2),
        "cpu": platform.processor() or platform.machine(),
        "torch": torch_v,
    }
    out = resolve(settings.paths.artifacts_dir, workdir()) / "vision"
    out.mkdir(parents=True, exist_ok=True)
    (out / "benchmark.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    _figure(a, res, out / "latence_vision.png")
    log.info("YOLO %s : moyenne %.1f ms, p95 %.1f ms (%.1f FPS) — budget %d ms : %s",
             res["resolution"], res["mean_ms"], res["p95_ms"], res["fps"], BUDGET_MS,
             "OK" if res["within_budget"] else "DÉPASSÉ")
    log.info("Résultats : %s", out)
    return res


def _figure(lat: np.ndarray, res: dict, path: Path) -> None:
    from .. import plotting as P
    import matplotlib.pyplot as plt
    P.setup()
    fig, ax = plt.subplots(figsize=(9, 3.4))
    ax.hist(lat, bins=30, color=P.BLUE, alpha=0.12, histtype="stepfilled")
    ax.hist(lat, bins=30, color=P.BLUE, lw=1.5, histtype="step")
    ax.axvline(BUDGET_MS, color=P.CRITICAL, lw=1.5)
    ax.text(BUDGET_MS, ax.get_ylim()[1] * 0.95, " budget 100 ms (cahier des charges)",
            color=P.INK2, fontsize=8.5, va="top")
    ax.axvline(res["p95_ms"], color=P.INK2, lw=1)
    ax.text(res["p95_ms"], ax.get_ylim()[1] * 0.75, f" p95 = {res['p95_ms']:.0f} ms",
            color=P.INK2, fontsize=8.5, va="top")
    ax.set_xlim(0, max(BUDGET_MS * 1.3, float(lat.max()) * 1.1))
    ax.set_xlabel("temps d'inférence par image (ms)")
    ax.set_ylabel("images")
    ax.set_title(f"Latence YOLOv8n sur CPU, images {res['resolution']} — "
                 f"{res['fps']:.0f} images/s en moyenne")
    fig.tight_layout()
    P.save(fig, path)
