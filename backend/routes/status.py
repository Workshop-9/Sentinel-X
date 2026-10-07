import time

from fastapi import APIRouter, Query

from .. import db

router = APIRouter(tags=["Status"])


@router.get("/api/v1/status")
def get_status(offline_after_s: int = Query(30, ge=1, le=3600)):
    now = int(time.time())
    with db.get_conn() as conn:
        device = conn.execute(
            "SELECT * FROM devices ORDER BY last_seen DESC LIMIT 1"
        ).fetchone()
        latest = conn.execute(
            "SELECT label FROM telemetry ORDER BY id DESC LIMIT 1"
        ).fetchone()

    state_by_label = {"normal": "NORMAL", "warning": "WARNING", "critical": "ALERT"}
    return {
        "device_id": device["device_id"] if device else None,
        "state": state_by_label.get(latest["label"], "NORMAL") if latest else "NORMAL",
        "online": bool(device and now - device["last_seen"] <= offline_after_s),
        "rssi_dbm": None,
    }