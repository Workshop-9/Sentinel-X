import numpy as np
import pytest

from sentinel_ai.anomaly.registry import IntegrityError, Registry


def test_save_load_roundtrip_and_promote(tmp_path, bundle):
    reg = Registry(tmp_path / "anomaly")
    version, vdir = reg.new_version("isolation_forest")
    bundle.version = version
    reg.save(bundle, vdir, {"test_fpr": 0.01}, promote=True)
    loaded = reg.load()
    assert loaded.version == version
    x = np.zeros((1, len(bundle.features)))
    assert loaded.score(x)[0] == pytest.approx(bundle.score(x)[0])
    assert reg.read()["production"] == version


def test_tampered_model_is_refused(tmp_path, bundle):
    reg = Registry(tmp_path / "anomaly")
    version, vdir = reg.new_version("isolation_forest")
    bundle.version = version
    reg.save(bundle, vdir, {}, promote=True)
    with open(vdir / "model.joblib", "ab") as fh:
        fh.write(b"malicious")
    with pytest.raises(IntegrityError):
        reg.load()


def test_unknown_version_cannot_be_promoted(tmp_path):
    with pytest.raises(KeyError):
        Registry(tmp_path / "anomaly").promote("nope")
