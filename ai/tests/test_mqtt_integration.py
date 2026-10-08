"""Bout en bout sur un vrai client paho : simulateur -> broker -> service anomalies -> sirène."""
from __future__ import annotations

import csv
import json
import threading
import time

import paho.mqtt.client as mqtt
import pytest

from sentinel_ai.config import load_settings
from sentinel_ai.paths import workdir

from .mini_broker import MiniBroker


@pytest.fixture
def env(monkeypatch):
    broker = MiniBroker(users={"ia": "secret"})
    monkeypatch.setenv("SENTINEL_MQTT_HOST", "127.0.0.1")
    monkeypatch.setenv("SENTINEL_MQTT_PORT", str(broker.port))
    monkeypatch.setenv("SENTINEL_MQTT_TLS", "false")
    monkeypatch.setenv("SENTINEL_MQTT_USER", "ia")
    monkeypatch.setenv("SENTINEL_MQTT_PASS", "secret")
    yield broker, load_settings()
    broker.stop()


def wait_for(cond, timeout=20.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def background(target, *args, **kwargs):
    t = threading.Thread(target=target, args=args, kwargs=kwargs, daemon=True)
    t.start()
    return t


def test_simulated_gas_leak_triggers_alarm_end_to_end(env):
    broker, settings = env
    from sentinel_ai.anomaly.service import run as run_anomaly
    from sentinel_ai.tools.simulate import run as run_simulator

    background(run_anomaly, settings)
    assert wait_for(lambda: any(t == "sentinel/SX-001/ai/anomaly/status" and p == b"online"
                                for t, p in broker.log)), "le service IA doit annoncer « online »"

    run_simulator(settings, scenario="fuite_gaz", at_s=60, duration_s=120, device="SX-SIM",
                  offline=False, speed=0)

    def anomalies():
        return [json.loads(p) for t, p in broker.log if t == "sentinel/SX-SIM/anomaly"]

    assert wait_for(lambda: any(a["level"] == "alarm" for a in anomalies()))
    cmds = [json.loads(p) for t, p in broker.log if t == "sentinel/SX-SIM/cmd"]
    assert cmds == [{"alarm": "on"}], "une seule commande sirène par incident"
    first_alarm = next(a for a in anomalies() if a["level"] == "alarm")
    assert any("gaz" in c for c in first_alarm["causes"])
    assert all(a["device_id"] == "SX-SIM" for a in anomalies())


def test_alarm_command_is_acknowledged(env):
    broker, settings = env
    from sentinel_ai.tools.alarm import run as run_alarm
    run_alarm(settings, "off", "SX-001")
    assert ("sentinel/SX-001/cmd", b'{"alarm": "off"}') in broker.log


def test_wrong_password_is_reported(env, monkeypatch):
    broker, _ = env
    monkeypatch.setenv("SENTINEL_MQTT_PASS", "wrong")
    settings = load_settings()
    from sentinel_ai.tools.alarm import run as run_alarm
    with pytest.raises(ConnectionError):
        run_alarm(settings, "on", "SX-001")
    assert not any(t.endswith("/cmd") for t, _ in broker.log)


def test_collector_writes_csv(env):
    broker, settings = env
    from sentinel_ai.tools.collector import run as run_collector
    background(run_collector, settings, "normal", 0.02)
    assert wait_for(lambda: len(broker.subs) >= 1)
    pub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    pub.username_pw_set("ia", "secret")
    pub.connect("127.0.0.1", broker.port)
    pub.loop_start()
    for i in range(5):
        pub.publish("sentinel/SX-001/telemetry",
                    json.dumps({"temp": 24.0 + i / 10, "hum": 50, "gas": 49, "motion": 1}))
        time.sleep(0.4)
    pub.publish("sentinel/SX-001/telemetry", json.dumps({"temp": None, "hum": 50, "gas": 49}))
    pub.loop_stop()
    path = workdir() / "data" / "telemetry.csv"
    assert wait_for(lambda: path.exists() and len(path.read_text(encoding="utf-8").splitlines()) >= 3)
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    assert rows[0]["label"] == "normal" and rows[0]["device_id"] == "SX-001"
    assert all(r["temp"] not in ("", "None") for r in rows)
