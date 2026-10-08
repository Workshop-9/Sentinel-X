import json
import time
import urllib.error
import urllib.request

import pytest

from sentinel_ai.vision.detector import TemporalConfirm
from sentinel_ai.vision.service import cleanup_captures
from sentinel_ai.vision.stream import FrameStore, StreamServer


def test_temporal_confirmation_filters_single_frames():
    c = TemporalConfirm(needed=3, window=5)
    assert [c.update(x) for x in (True, False, True, False)] == [False] * 4
    assert c.update(True) is True        # 3 détections sur les 5 dernières images
    assert [c.update(False) for _ in range(3)] == [False] * 3


def test_confirm_rejects_impossible_settings():
    with pytest.raises(ValueError):
        TemporalConfirm(needed=6, window=5)


def test_old_captures_are_deleted(tmp_path):
    old, new = tmp_path / "intrus_old.jpg", tmp_path / "intrus_new.jpg"
    for p in (old, new):
        p.write_bytes(b"x")
    past = time.time() - 10 * 86400
    import os
    os.utime(old, (past, past))
    assert cleanup_captures(tmp_path, days=7) == 1
    assert new.exists() and not old.exists()


@pytest.fixture
def server():
    store = FrameStore()
    srv = StreamServer(store, "127.0.0.1", 0, token="t0k3n", max_clients=1, fps=20).start()
    port = srv.httpd.server_address[1]
    yield store, f"http://127.0.0.1:{port}"
    srv.stop()


def get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def test_stream_requires_token(server):
    _, base = server
    assert get(f"{base}/health")[0] == 401
    assert get(f"{base}/health?token=wrong")[0] == 401
    assert get(f"{base}/health?token=t0k3n")[0] == 200
    assert get(f"{base}/health", {"Authorization": "Bearer t0k3n"})[0] == 200


def test_snapshot_health_and_no_version_banner(server):
    store, base = server
    assert get(f"{base}/snapshot.jpg?token=t0k3n")[0] == 503
    store.update(b"\xff\xd8jpeg", persons=1, fps=12.0)
    status, headers, body = get(f"{base}/snapshot.jpg?token=t0k3n")
    assert status == 200 and body == b"\xff\xd8jpeg"
    assert headers["Server"].strip() == "SentinelX"
    assert headers["Cache-Control"] == "no-store"
    status, _, body = get(f"{base}/health?token=t0k3n")
    assert json.loads(body)["persons"] == 1
    assert get(f"{base}/admin?token=t0k3n")[0] == 404
