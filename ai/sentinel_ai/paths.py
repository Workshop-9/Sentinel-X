"""Emplacements des fichiers.

Le dossier ai/ peut être protégé en écriture par Windows (« Contrôle d'accès aux
dossiers » sur Documents). Tout ce qui est écrit pendant l'exécution (données
collectées, modèles, rapports) va donc dans un *dossier de travail* :

1. la variable d'environnement SENTINEL_HOME si elle est définie ;
2. sinon le dossier ai/ lui-même s'il est inscriptible ;
3. sinon ~/sentinel_x (hors Documents).

La lecture regarde le dossier de travail puis le dépôt, pour que le modèle livré
dans artifacts/ fonctionne même quand ai/ est en lecture seule.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)

REPO_DIR = Path(__file__).resolve().parents[1]
FALLBACK_HOME = Path.home() / "sentinel_x"


def is_writable(directory: Path) -> bool:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / f".write_probe_{os.getpid()}"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


@lru_cache(maxsize=1)
def workdir() -> Path:
    env = os.getenv("SENTINEL_HOME")
    if env:
        home = Path(env).expanduser().resolve()
        home.mkdir(parents=True, exist_ok=True)
        return home
    if is_writable(REPO_DIR):
        return REPO_DIR
    FALLBACK_HOME.mkdir(parents=True, exist_ok=True)
    log.warning("Dossier %s protégé en écriture (Windows) : sorties écrites dans %s",
                REPO_DIR, FALLBACK_HOME)
    return FALLBACK_HOME


def resolve(path: str | Path, base: Path = REPO_DIR) -> Path:
    """Chemin de config -> chemin absolu (~ accepté, relatif au dossier ai/)."""
    p = Path(path).expanduser()
    return p if p.is_absolute() else base / p


def read_locations(relative: str | Path) -> list[Path]:
    """Emplacements à lire, par priorité : dossier de travail puis dépôt."""
    out: list[Path] = []
    for base in (workdir(), REPO_DIR):
        p = resolve(relative, base)
        if p not in out:
            out.append(p)
    return out
