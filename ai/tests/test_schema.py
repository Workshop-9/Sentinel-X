import math

import pytest

from sentinel_ai.data.schema import device_from_topic, parse_reading

VALID = {"device_id": "SX-001", "ts": 1, "temp": 26.1, "hum": 48.0, "gas": 60, "motion": 0}


def test_valid_message():
    r = parse_reading(VALID)
    assert (r.device_id, r.temp, r.hum, r.gas, r.motion) == ("SX-001", 26.1, 48.0, 60.0, 0)


@pytest.mark.parametrize("field,value", [
    ("temp", None), ("temp", "abc"), ("temp", math.nan), ("hum", 120), ("gas", -1),
    ("gas", 5000), ("temp", True),
])
def test_invalid_measure_rejected(field, value):
    assert parse_reading({**VALID, field: value}) is None


def test_numeric_strings_accepted_and_device_defaulted():
    r = parse_reading({"temp": "25.0", "hum": "40", "gas": "100"}, default_device="SX-002")
    assert r.device_id == "SX-002" and r.temp == 25.0


def test_topic_identity_wins_over_payload():
    r = parse_reading({**VALID, "device_id": "SX-001"}, topic_device="SX-002")
    assert r.device_id == "SX-002"


def test_non_dict_rejected():
    assert parse_reading([1, 2, 3]) is None


def test_device_from_topic():
    assert device_from_topic("sentinel/SX-001/telemetry") == "SX-001"
    assert device_from_topic("bad") is None
