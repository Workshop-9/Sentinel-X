from sentinel_ai.anomaly.detector import ALARM, NORMAL, AnomalyDetector

from .conftest import normal_signal


def feed(det, df, start_t=0.0):
    out = []
    for i, r in enumerate(df.itertuples()):
        out.append(det.step(r.temp, r.hum, r.gas, t=start_t + 2.0 * i))
    return out


def test_normal_signal_raises_no_confirmed_alarm(bundle):
    det = AnomalyDetector(bundle, consecutive=3)
    decisions = [d for d in feed(det, normal_signal(600, seed=7)) if d]
    assert decisions
    assert not any(d.alarm_triggered for d in decisions)


def test_gas_leak_triggers_alarm_once_with_explanation(bundle):
    det = AnomalyDetector(bundle, consecutive=3)
    feed(det, normal_signal(200, seed=3))
    leak = [det.step(24.2, 53.0, 50.0 + 15 * k, t=400 + 2 * k) for k in range(1, 12)]
    triggered = [d for d in leak if d.alarm_triggered]
    assert len(triggered) == 1, "la sirène ne doit être déclenchée qu'une fois par incident"
    assert triggered[0].level == ALARM
    assert any("gaz" in c["label"] for c in triggered[0].causes)


def test_baseline_frozen_during_anomaly_and_recovers(bundle):
    det = AnomalyDetector(bundle, consecutive=3, max_freeze=150)
    feed(det, normal_signal(200, seed=4))
    base_gas = det.extractor.baseline[2]
    for k in range(30):                                  # 60 s de fuite
        det.step(24.2, 53.0, 170.0, t=400 + 2 * k)
    assert abs(det.extractor.baseline[2] - base_gas) < 1.0, "ligne de base gelée"
    after = [det.step(r.temp, r.hum, r.gas, t=460 + 2 * i)
             for i, r in enumerate(normal_signal(60, seed=5).itertuples())]
    assert after[-1].level == NORMAL


def test_extreme_single_feature_is_always_anomalous(bundle):
    """Garde-fou contre la saturation de l'Isolation Forest hors domaine."""
    import numpy as np
    sc = bundle.pipeline.named_steps["scaler"]
    for j in range(len(bundle.features)):
        x = sc.mean_.copy()
        x[j] += 100 * sc.scale_[j]
        assert bundle.score(x[None])[0] < 0, bundle.features[j]
    assert bundle.score(sc.mean_[None])[0] > 0
    assert np.isfinite(bundle.envelope["z_max"])


def test_long_anomaly_is_eventually_relearned(bundle):
    det = AnomalyDetector(bundle, consecutive=3, max_freeze=20)
    feed(det, normal_signal(200, seed=6))
    base_gas = det.extractor.baseline[2]
    for k in range(200):
        det.step(24.2, 53.0, 120.0, t=400 + 2 * k)
    assert det.extractor.baseline[2] > base_gas + 20
