import json

from sentinel_ai.anomaly.service import AnomalyService
from sentinel_ai.config import Settings

from .conftest import normal_signal

TOPIC = "sentinel/SX-001/telemetry"


def msg(temp, hum, gas):
    return json.dumps({"device_id": "SX-001", "temp": temp, "hum": hum, "gas": gas, "motion": 0})


def test_invalid_payloads_are_ignored(bundle):
    svc = AnomalyService(Settings(), bundle)
    assert svc.handle(TOPIC, b"not json") == []
    assert svc.handle(TOPIC, json.dumps({"temp": None, "hum": 1, "gas": 1})) == []
    assert svc.invalid == 2


def test_message_contract_and_auto_alarm(bundle):
    svc = AnomalyService(Settings(), bundle, auto_alarm=True)
    out = []
    for i, r in enumerate(normal_signal(100, seed=2).itertuples()):
        out += svc.handle(TOPIC, msg(r.temp, r.hum, r.gas), now=1000 + 2 * i)
    topics = {t for t, *_ in out}
    assert topics == {"sentinel/SX-001/anomaly"}
    first = json.loads(out[0][1])
    for key in ("device_id", "ts", "score", "is_anomaly", "streak", "level", "causes", "model"):
        assert key in first
    alarms = []
    for k in range(1, 10):
        alarms += [m for m in svc.handle(TOPIC, msg(24.2, 53.0, 50 + 20 * k), now=1300 + 2 * k)
                   if m[0].endswith("/cmd")]
    assert len(alarms) == 1
    assert json.loads(alarms[0][1]) == {"alarm": "on"} and alarms[0][2] == 1


def test_devices_are_tracked_separately(bundle):
    svc = AnomalyService(Settings(), bundle)
    svc.handle("sentinel/SX-001/telemetry", msg(24, 50, 50), now=0)
    svc.handle("sentinel/SX-002/telemetry", msg(24, 50, 50), now=0)
    assert set(svc.detectors) == {"SX-001", "SX-002"}


def test_no_alarm_when_disabled(bundle):
    svc = AnomalyService(Settings(), bundle, auto_alarm=False)
    for i, r in enumerate(normal_signal(100, seed=2).itertuples()):
        svc.handle(TOPIC, msg(r.temp, r.hum, r.gas), now=2 * i)
    out = []
    for k in range(1, 10):
        out += svc.handle(TOPIC, msg(24.2, 53.0, 50 + 20 * k), now=300 + 2 * k)
    assert not [m for m in out if m[0].endswith("/cmd")]
