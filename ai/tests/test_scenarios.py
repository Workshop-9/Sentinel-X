import numpy as np

from sentinel_ai.data.scenarios import SCENARIOS, inject

from .conftest import normal_signal


def test_injection_adds_offsets_and_keeps_plateau():
    df = normal_signal(200)
    sc = SCENARIOS["fuite_gaz"]
    out = inject(df, 50, sc)
    np.testing.assert_allclose(out["gas"].iloc[:50], df["gas"].iloc[:50])
    assert out["gas"].iloc[50 + sc.length - 1] - df["gas"].iloc[50 + sc.length - 1] == 120
    assert out["gas"].iloc[-1] - df["gas"].iloc[-1] == 120
    np.testing.assert_allclose(out["temp"], df["temp"])


def test_slow_overheat_stays_below_static_rule():
    sc = SCENARIOS["surchauffe_lente"]
    off = sc.offsets()
    assert off["temp"].max() == 2.0 and off["gas"].max() == 6.0


def test_values_clipped_to_physical_range():
    df = normal_signal(100).assign(gas=1000.0, hum=95.0)
    out = inject(df, 0, SCENARIOS["fuite_gaz"])
    assert out["gas"].max() <= 1024
    out = inject(df, 0, SCENARIOS["infiltration_humidite"])
    assert out["hum"].max() <= 100
