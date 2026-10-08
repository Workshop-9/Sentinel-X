"""Chargement de la configuration : config/settings.toml + .env + variables d'environnement.

Les secrets (identifiants MQTT, jeton vidéo) ne sont lus que depuis l'environnement
ou le fichier .env (ignoré par Git), jamais depuis le fichier TOML.
"""
from __future__ import annotations

import logging
import os
import tomllib
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, get_type_hints

from .paths import REPO_DIR

log = logging.getLogger(__name__)

DEFAULT_CONFIG = REPO_DIR / "config" / "settings.toml"
ENV_FILE = REPO_DIR / ".env"


@dataclass
class MqttSettings:
    host: str = "192.168.137.1"
    port: int = 8883
    tls: bool = True
    ca_cert: str = "certs/ca.crt"
    tls_check_hostname: bool = True
    keepalive: int = 30
    topic_telemetry: str = "sentinel/+/telemetry"
    topic_anomaly: str = "sentinel/{device}/anomaly"
    topic_vision: str = "sentinel/{device}/vision"
    topic_cmd: str = "sentinel/{device}/cmd"
    topic_ai_status: str = "sentinel/{device}/ai/{service}/status"
    username: str = ""
    password: str = field(default="", repr=False)

    @property
    def has_credentials(self) -> bool:
        return bool(self.username and self.password)


@dataclass
class PathSettings:
    data_dir: str = "data"
    artifacts_dir: str = "artifacts"
    captures_dir: str = "~/sentinel_captures"


@dataclass
class FeatureSettings:
    window: int = 15
    baseline_halflife: float = 150
    reset_after_s: float = 600


@dataclass
class ModelSettings:
    algorithm: str = "isolation_forest"
    n_estimators: int = 200
    random_state: int = 42


@dataclass
class TrainingSettings:
    train_frac: float = 0.6
    calib_frac: float = 0.2
    target_fpr: float = 0.01
    benchmark: list[str] = field(default_factory=lambda: [
        "isolation_forest", "lof", "ocsvm", "robust_covariance"])


@dataclass
class GateSettings:
    max_false_alarms_per_hour: float = 2.0
    max_test_fpr: float = 0.10
    min_anomaly_recall: float = 0.80
    min_scenarios_detected: float = 0.75
    min_plateau_coverage: float = 0.90


@dataclass
class LiveSettings:
    consecutive: int = 3
    auto_alarm: bool = True
    max_freeze: int = 150


@dataclass
class AnomalySettings:
    features: FeatureSettings = field(default_factory=FeatureSettings)
    model: ModelSettings = field(default_factory=ModelSettings)
    training: TrainingSettings = field(default_factory=TrainingSettings)
    gates: GateSettings = field(default_factory=GateSettings)
    live: LiveSettings = field(default_factory=LiveSettings)


@dataclass
class StreamSettings:
    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 8081
    max_clients: int = 4
    fps: float = 10
    token: str = field(default="", repr=False)


@dataclass
class VisionSettings:
    camera_index: int = 1
    weights: str = "models/yolov8n.pt"
    conf_min: float = 0.5
    frame_width: int = 640
    frame_height: int = 480
    confirm_frames: int = 3
    confirm_window: int = 5
    cooldown_s: float = 10
    auto_alarm: bool = False
    show_window: bool = True
    captures_retention_days: int = 7
    stream: StreamSettings = field(default_factory=StreamSettings)


@dataclass
class Settings:
    device_id: str = "SX-001"
    mqtt: MqttSettings = field(default_factory=MqttSettings)
    paths: PathSettings = field(default_factory=PathSettings)
    anomaly: AnomalySettings = field(default_factory=AnomalySettings)
    vision: VisionSettings = field(default_factory=VisionSettings)

    def topic(self, name: str, device: str | None = None, service: str = "") -> str:
        template = getattr(self.mqtt, f"topic_{name}")
        return template.format(device=device or self.device_id, service=service)


def _build(cls: type, data: dict[str, Any], where: str) -> Any:
    hints = get_type_hints(cls)
    kwargs = {}
    known = {f.name for f in fields(cls)}
    for key in data:
        if key not in known:
            log.warning("Clé inconnue ignorée dans la config : %s.%s", where, key)
    for f in fields(cls):
        if f.name not in data:
            continue
        value = data[f.name]
        ftype = hints[f.name]
        if is_dataclass(ftype):
            kwargs[f.name] = _build(ftype, value, f"{where}.{f.name}")
        else:
            kwargs[f.name] = value
    return cls(**kwargs)


def load_dotenv(path: Path = ENV_FILE) -> None:
    """Lit un fichier KEY=VALUE minimal (sans écraser l'environnement existant)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if value:
            os.environ.setdefault(key.strip(), value)


def _env_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on", "oui"}


def load_settings(path: str | Path | None = None) -> Settings:
    load_dotenv()
    cfg_path = Path(path) if path else DEFAULT_CONFIG
    raw: dict[str, Any] = {}
    if cfg_path.exists():
        with open(cfg_path, "rb") as fh:
            raw = tomllib.load(fh)
    elif path:
        raise FileNotFoundError(f"Fichier de configuration introuvable : {cfg_path}")

    device = raw.pop("device", {})
    settings = _build(Settings, raw, "settings")
    settings.device_id = device.get("id", settings.device_id)

    env = os.environ
    m = settings.mqtt
    m.host = env.get("SENTINEL_MQTT_HOST", m.host)
    m.port = int(env.get("SENTINEL_MQTT_PORT", m.port))
    if "SENTINEL_MQTT_TLS" in env:
        m.tls = _env_bool(env["SENTINEL_MQTT_TLS"])
    m.username = env.get("SENTINEL_MQTT_USER", m.username)
    m.password = env.get("SENTINEL_MQTT_PASS", m.password)
    settings.vision.stream.token = env.get("SENTINEL_STREAM_TOKEN", settings.vision.stream.token)
    return settings
