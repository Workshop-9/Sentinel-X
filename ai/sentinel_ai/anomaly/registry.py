"""Registre de modèles versionnés.

artifacts/anomaly/
├── registry.json                 version en production + historique
└── <version>/
    ├── model.joblib              bundle (pipeline + seuil + paramètres features)
    ├── metrics.json, benchmark.csv, data_profile.json
    ├── model_card.md, report.html
    └── figures/*.png

L'empreinte SHA-256 de chaque modèle est vérifiée avant chargement : un fichier
remplacé ou altéré (ex. pendant le pentest) est refusé.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib

from ..paths import read_locations, resolve, workdir
from .models import ModelBundle

log = logging.getLogger(__name__)

SUBDIR = "anomaly"
REGISTRY_FILE = "registry.json"


class IntegrityError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Registry:
    def __init__(self, root: Path):
        self.root = root
        self.file = root / REGISTRY_FILE

    @classmethod
    def for_writing(cls, artifacts_dir: str) -> "Registry":
        return cls(resolve(artifacts_dir, workdir()) / SUBDIR)

    def read(self) -> dict[str, Any]:
        if not self.file.exists():
            return {"production": None, "models": {}}
        return json.loads(self.file.read_text(encoding="utf-8"))

    def write(self, data: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def new_version(self, algorithm: str) -> tuple[str, Path]:
        short = {"isolation_forest": "iforest", "robust_covariance": "robustcov"}.get(algorithm, algorithm)
        version = f"{short}-{datetime.now():%Y%m%d-%H%M%S}"
        path = self.root / version
        (path / "figures").mkdir(parents=True, exist_ok=True)
        return version, path

    def save(self, bundle: ModelBundle, version_dir: Path, summary: dict[str, Any],
             promote: bool) -> str:
        model_path = version_dir / "model.joblib"
        joblib.dump(bundle.to_dict(), model_path, compress=3)
        digest = sha256(model_path)
        data = self.read()
        data["models"][bundle.version] = {
            "created": datetime.now().isoformat(timespec="seconds"),
            "algorithm": bundle.algorithm,
            "path": f"{bundle.version}/model.joblib",
            "sha256": digest,
            "summary": summary,
        }
        if promote:
            data["production"] = bundle.version
        self.write(data)
        return digest

    def promote(self, version: str) -> None:
        data = self.read()
        if version not in data["models"]:
            raise KeyError(f"Version inconnue : {version}")
        data["production"] = version
        self.write(data)

    def load(self, version: str | None = None) -> ModelBundle:
        data = self.read()
        version = version or data.get("production")
        if not version or version not in data["models"]:
            raise FileNotFoundError(f"Aucun modèle « {version or 'production'} » dans {self.file}")
        entry = data["models"][version]
        path = self.root / entry["path"]
        if sha256(path) != entry["sha256"]:
            raise IntegrityError(f"Empreinte SHA-256 invalide pour {path} : fichier modifié, refusé")
        bundle = ModelBundle.from_dict(joblib.load(path))
        bundle.metadata.setdefault("path", str(path))
        return bundle


def production_registry(artifacts_dir: str) -> Registry:
    """Premier registre (dossier de travail, puis dépôt) ayant un modèle en production."""
    for base in read_locations(artifacts_dir):
        reg = Registry(base / SUBDIR)
        if reg.read().get("production"):
            return reg
    raise FileNotFoundError(
        "Aucun modèle en production : lance « python -m sentinel_ai train »")


def load_production(artifacts_dir: str) -> ModelBundle:
    reg = production_registry(artifacts_dir)
    bundle = reg.load()
    log.info("Modèle %s chargé (%s, intégrité SHA-256 OK) depuis %s",
             bundle.version, bundle.algorithm, reg.root)
    return bundle
