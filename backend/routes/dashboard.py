import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from .. import db
from .formatters import iso_timestamp

router = APIRouter(tags=["Dashboard"])


@router.get("/api/v1/events")
def get_events(
    limit: int = Query(100, ge=1, le=1000),
    type: Optional[str] = None,
    state: Optional[str] = None,
):
    query = "SELECT * FROM events WHERE 1=1"
    params = []
    if type:
        query += " AND type=%s"
        params.append(type)
    if state:
        query += " AND state=%s"
        params.append(state)
    query += " ORDER BY ts DESC LIMIT %s"
    params.append(limit)
    with db.get_conn() as conn:
        return [dict(row) for row in conn.execute(query, params)]


@router.get("/api/v1/telemetry")
def get_telemetry(
    limit: int = Query(200, ge=1, le=2000),
    since: Optional[str] = None,
):
    query = "SELECT * FROM telemetry"
    params = []
    if since:
        try:
            since_timestamp = int(datetime.fromisoformat(since.replace("Z", "+00:00")).timestamp())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid since timestamp") from exc
        query += " WHERE ts >= %s"
        params.append(since_timestamp)
    query += " ORDER BY ts DESC LIMIT %s"
    params.append(limit)

    with db.get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return {
        "items": [
            {
                "received_at": iso_timestamp(row["ts"]),
                "sensors": {
                    "temperature_c": row["temperature"],
                    "gas_ppm": row["gas"],
                    "humidity_pct": row["humidity"],
                },
            }
            for row in reversed(rows)
        ]
    }


@router.get("/api/v1/alerts")
def get_alerts(limit: int = Query(50, ge=1, le=1000)):
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM events ORDER BY ts DESC LIMIT %s", (limit,)
        ).fetchall()

    severity_by_state = {"OK": "info", "WARNING": "warning", "CRITICAL": "critical"}
    return {
        "items": [
            {
                "id": row["id"],
                "type": row["type"],
                "severity": severity_by_state[row["state"]],
                "event": "cleared" if row["state"] == "OK" else "raised",
                "source": row["device_id"],
                "received_at": iso_timestamp(row["received_at"]),
                "acknowledged": False,
                "value": row["value"],
                "unit": row["unit"],
            }
            for row in rows
        ]
    }


@router.get("/api/v1/status")
def get_status(offline_after_s: int = Query(30, ge=1, le=3600)):
    now = int(time.time())
    with db.get_conn() as conn:
        device = conn.execute(
            "SELECT * FROM devices ORDER BY last_seen DESC LIMIT 1"
        ).fetchone()
        latest_event = conn.execute(
            "SELECT state FROM events ORDER BY ts DESC LIMIT 1"
        ).fetchone()

    state_by_backend = {"OK": "NORMAL", "WARNING": "WARNING", "CRITICAL": "ALERT"}
    return {
        "device_id": device["device_id"] if device else None,
        "state": state_by_backend.get(latest_event["state"], "NORMAL") if latest_event else "NORMAL",
        "online": bool(device and now - device["last_seen"] <= offline_after_s),
        "rssi_dbm": None,
    }