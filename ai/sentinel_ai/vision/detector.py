"""Détecteur de personnes (YOLOv8n) + confirmation sur plusieurs images."""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import numpy as np

PERSON_CLASS = 0   # COCO : 0 = person


@dataclass
class Detection:
    persons: int
    confidence: float           # meilleure confiance (0 si personne)
    boxes: np.ndarray           # (n, 4) x1 y1 x2 y2
    inference_ms: float
    annotated: np.ndarray       # image avec les cadres dessinés


class PersonDetector:
    def __init__(self, weights: Path, conf_min: float = 0.5, imgsz: int = 640):
        from ultralytics import YOLO          # import lourd (torch) : seulement si besoin
        if not Path(weights).exists():
            raise FileNotFoundError(
                f"Poids YOLO introuvables : {weights}. Télécharge yolov8n.pt "
                "(https://github.com/ultralytics/assets/releases) dans ai/models/")
        self.model = YOLO(str(weights))
        self.conf_min = conf_min
        self.imgsz = imgsz
        self(np.zeros((480, 640, 3), dtype=np.uint8))   # préchauffage : 1re image sans latence

    def __call__(self, frame: np.ndarray) -> Detection:
        t0 = time.perf_counter()
        result = self.model(frame, classes=[PERSON_CLASS], conf=self.conf_min,
                            imgsz=self.imgsz, verbose=False)[0]
        ms = (time.perf_counter() - t0) * 1000
        boxes = result.boxes
        n = len(boxes)
        return Detection(
            persons=n,
            confidence=float(boxes.conf.max()) if n else 0.0,
            boxes=boxes.xyxy.cpu().numpy() if n else np.empty((0, 4)),
            inference_ms=ms,
            annotated=result.plot(),
        )


class TemporalConfirm:
    """Présence confirmée si une personne est vue sur au moins `needed` des `window`
    dernières images : élimine les faux positifs d'une seule image (reflet, ombre)."""

    def __init__(self, needed: int = 3, window: int = 5):
        if needed > window:
            raise ValueError("confirm_frames doit être <= confirm_window")
        self.needed = needed
        self.history: deque[bool] = deque(maxlen=window)

    def update(self, seen: bool) -> bool:
        self.history.append(seen)
        return sum(self.history) >= self.needed
