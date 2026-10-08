import numpy as np
import pytest

from sentinel_ai.anomaly.features import FEATURES, OnlineFeatureExtractor

from .conftest import FEATURE_PARAMS, features_of, normal_signal


def test_no_features_until_window_full():
    ex = OnlineFeatureExtractor(**FEATURE_PARAMS)
    outputs = [ex.update(24.0, 50.0, 50.0) for _ in range(15)]
    assert all(o is None for o in outputs)
    assert ex.update(24.0, 50.0, 50.0) is not None


def test_kinetic_features_match_pandas_reference():
    df = normal_signal(200)
    feats = features_of(df)
    ref = df.copy()
    ref["d_gas"] = ref["gas"].diff(15)
    ref["gas_std"] = ref["gas"].rolling(15).std()
    ref = ref.dropna(subset=["d_gas", "gas_std"]).reset_index(drop=True)
    np.testing.assert_allclose(feats["d_gas"], ref["d_gas"])
    np.testing.assert_allclose(feats["gas_std"], ref["gas_std"])


def test_features_invariant_to_site_offset():
    """Même dynamique dans une autre salle (+3 °C, -10 % HR, +25 gaz) => mêmes features."""
    df = normal_signal(300)
    shifted = df.assign(temp=df.temp + 3, hum=df.hum - 10, gas=df.gas + 25)
    np.testing.assert_allclose(features_of(df)[FEATURES], features_of(shifted)[FEATURES], atol=1e-9)


def test_deviation_reacts_to_level_change():
    ex = OnlineFeatureExtractor(**FEATURE_PARAMS)
    for _ in range(100):
        ex.update(24.0, 50.0, 50.0)
    f = ex.update(24.0, 50.0, 150.0)
    assert f["gas_dev"] == pytest.approx(100.0)
    assert f["d_gas"] == pytest.approx(100.0)


def test_long_gap_resets_context():
    ex = OnlineFeatureExtractor(**FEATURE_PARAMS)
    for i in range(30):
        ex.update(24.0, 50.0, 50.0, t=i * 2.0)
    assert ex.ready
    ex.update(30.0, 50.0, 50.0, t=60 + 601)
    assert not ex.ready
    assert ex.baseline[0] == pytest.approx(30.0)


def test_short_gap_keeps_context():
    ex = OnlineFeatureExtractor(**FEATURE_PARAMS)
    for i in range(30):
        ex.update(24.0, 50.0, 50.0, t=i * 2.0)
    assert ex.update(24.0, 50.0, 50.0, t=60 + 200) is not None


def test_no_adapt_freezes_baseline():
    ex = OnlineFeatureExtractor(**FEATURE_PARAMS)
    for _ in range(50):
        ex.update(24.0, 50.0, 50.0)
    before = ex.baseline.copy()
    ex.update(24.0, 50.0, 500.0, adapt=False)
    np.testing.assert_array_equal(ex.baseline, before)


def test_bias_corrected_start_is_running_mean():
    ex = OnlineFeatureExtractor(**FEATURE_PARAMS)
    values = [40.0, 50.0, 60.0]
    for v in values:
        ex.update(24.0, 50.0, v)
    assert ex.baseline[2] == pytest.approx(np.mean(values))
