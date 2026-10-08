"""Journalisation homogène pour tous les services."""
from __future__ import annotations

import logging
import sys

FORMAT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"


def setup_logging(verbose: bool = False) -> None:
    # Console Windows : forcer l'UTF-8 pour les accents
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format=FORMAT,
        datefmt="%H:%M:%S",
        stream=sys.stdout,
        force=True,
    )
    for noisy in ("matplotlib", "PIL", "ultralytics"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
