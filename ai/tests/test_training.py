"""Test d'intégration : le pipeline complet tourne sur les vraies données du dépôt."""
from sentinel_ai.anomaly.registry import load_production
from sentinel_ai.anomaly.train import train
from sentinel_ai.config import load_settings


def test_full_training_pipeline_on_repository_data(isolated_home):
    settings = load_settings()
    res = train(settings, make_report=False)
    m = res.metrics["metrics"]
    assert res.gates_passed and res.promoted
    assert m["test_false_alarms"] == 0
    assert m["anomaly_recall"] >= 0.8
    assert m["scenario_detection_rate"] >= 0.75
    assert res.metrics["metrics"]["site_shift_fpr"] < res.metrics["legacy_metrics"]["site_shift_fpr"]
    assert (res.directory / "metrics.json").exists()
    assert str(isolated_home) in str(res.directory), "les sorties doivent aller dans SENTINEL_HOME"
    assert load_production(settings.paths.artifacts_dir).version == res.version
