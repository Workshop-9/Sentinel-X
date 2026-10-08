import logging

from sentinel_ai import config


def test_repository_config_loads():
    s = config.load_settings()
    assert s.device_id == "SX-001"
    assert s.mqtt.tls is True and s.mqtt.port == 8883
    assert s.anomaly.features.window == 15
    assert s.vision.stream.host == "127.0.0.1"
    assert s.topic("anomaly", "SX-002") == "sentinel/SX-002/anomaly"


def test_secrets_only_from_environment(monkeypatch):
    monkeypatch.setenv("SENTINEL_MQTT_USER", "ia")
    monkeypatch.setenv("SENTINEL_MQTT_PASS", "s3cret")
    monkeypatch.setenv("SENTINEL_MQTT_TLS", "false")
    s = config.load_settings()
    assert s.mqtt.has_credentials and not s.mqtt.tls
    assert "s3cret" not in repr(s.mqtt), "le mot de passe ne doit jamais apparaître dans les logs"


def test_dotenv_does_not_override_environment(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("SENTINEL_MQTT_USER=from_file\n# commentaire\nSENTINEL_MQTT_PASS='p w'\n",
                   encoding="utf-8")
    monkeypatch.setenv("SENTINEL_MQTT_USER", "from_env")
    config.load_dotenv(env)
    import os
    assert os.environ["SENTINEL_MQTT_USER"] == "from_env"
    assert os.environ["SENTINEL_MQTT_PASS"] == "p w"


def test_unknown_key_warns(tmp_path, caplog):
    cfg = tmp_path / "s.toml"
    cfg.write_text('[device]\nid = "SX-009"\n[mqtt]\nhots = "typo"\n', encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        s = config.load_settings(cfg)
    assert s.device_id == "SX-009"
    assert "mqtt.hots" in caplog.text
