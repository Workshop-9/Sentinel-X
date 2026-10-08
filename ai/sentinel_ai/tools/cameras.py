"""Trouve le numéro de la webcam USB (Logitech C270) : python -m sentinel_ai cameras"""
from __future__ import annotations

import logging
import threading

import cv2

log = logging.getLogger(__name__)
BACKENDS = {"DSHOW": cv2.CAP_DSHOW, "MSMF": cv2.CAP_MSMF}


def _try(index: int, backend: int, result: dict) -> None:
    cap = cv2.VideoCapture(index, backend)
    if cap.isOpened():
        ok, frame = cap.read()
        if ok:
            result["frame"] = frame
    cap.release()


def run(max_index: int = 4, preview: bool = True) -> list[tuple[int, str]]:
    found = []
    for name, backend in BACKENDS.items():
        for i in range(max_index):
            result: dict = {}
            t = threading.Thread(target=_try, args=(i, backend, result), daemon=True)
            t.start()
            t.join(timeout=5)                 # certaines caméras virtuelles bloquent
            if "frame" in result:
                found.append((i, name))
                log.info("Caméra %d (%s) : image reçue", i, name)
                if preview:
                    frame = result["frame"]
                    cv2.putText(frame, f"CAMERA {i} - {name}", (20, 50),
                                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
                    cv2.imshow("Test camera", frame)
                    cv2.waitKey(2500)
                    cv2.destroyAllWindows()
            elif t.is_alive():
                log.info("Caméra %d (%s) : bloquée (ignorée)", i, name)
            else:
                log.info("Caméra %d (%s) : rien", i, name)
    log.info("Mets le numéro de la Logitech dans config/settings.toml → [vision] camera_index")
    return found
