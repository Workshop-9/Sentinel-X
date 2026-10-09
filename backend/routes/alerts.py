import json
import time
from typing import Optional

from fastapi import APIRouter, Query, Response

from .. import db
from ..models import AlertIn, AnomalyIn, VisionAlertIn
from ..ws import manager
from .formatters import iso_timestamp, serialize_alert

router = APIRouter(tags=["Alerts"])
STATE_BY_LEVEL = {"normal": "OK", "suspect": "WARNING", "alarm": "CRITICAL"}
SEVERITY_BY_STATE = {"OK": "info", "WARNING": "warning", "CRITICAL": "critical"}


def store_anomaly(alert: AnomalyIn):
    state = STATE_BY_LEVEL[alert.level]
    details = {
        "score": alert.score,
        "is_anomaly": alert.is_anomaly,
        "streak": alert.streak,
        "causes": alert.causes,
        "model": alert.model,
    }
    with db.get_conn() as conn:
        previous = conn.execute(
            "SELECT state FROM events WHERE device_id=%s AND type='anomaly' "
            "ORDER BY ts DESC, id DESC LIMIT 1",
            (alert.device_id,),
        ).fetchone()
        if previous and previous["state"] == state:
            return None
        if state == "OK" and previous is None:
            return None

        received_at = int(time.time())
        cursor = conn.execute(
            "INSERT INTO events(device_id, ts, type, state, value, unit, received_at, details) "
            "VALUES(%s,%s,'anomaly',%s,%s,'score',%s,%s::jsonb) RETURNING id",
            (
                alert.device_id,
                alert.timestamp,
                state,
                alert.score,
                received_at,
                json.dumps(details),
            ),
        )
        db.touch_device(conn, alert.device_id)
        event_id = cursor.fetchone()["id"]

    return {
        "id": event_id,
        "type": "anomaly",
        "severity": SEVERITY_BY_STATE[state],
        "event": "cleared" if state == "OK" else "raised",
        "source": alert.device_id,
        "received_at": iso_timestamp(received_at),
        "acknowledged": False,
        "value": alert.score,
        "unit": "score",
        "details": details,
    }


def store_vision_alert(alert: VisionAlertIn):
    details = {
        "source": alert.source,
        "confidence": alert.confidence,
        "persons": alert.persons,
        "inference_ms": alert.inference_ms,
        "snapshot": alert.snapshot,
    }
    received_at = int(time.time())
    with db.get_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO events(device_id, ts, type, state, value, unit, received_at, details) "
            "VALUES(%s,%s,'intrusion','CRITICAL',%s,'confidence',%s,%s::jsonb) RETURNING id",
            (
                alert.device_id,
                alert.timestamp,
                alert.confidence,
                received_at,
                json.dumps(details),
            ),
        )
        db.touch_device(conn, alert.device_id)
        event_id = cursor.fetchone()["id"]

    return {
        "id": event_id,
        "type": "intrusion",
        "severity": "critical",
        "event": "raised",
        "source": alert.device_id,
        "received_at": iso_timestamp(received_at),
        "acknowledged": False,
        "value": alert.confidence,
        "unit": "confidence",
        "details": details,
    }


@router.post("/api/v1/alerts", status_code=201)
async def post_alert(alert: AlertIn):
    with db.get_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO events(device_id, ts, type, state, value, unit, received_at) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (
                alert.device_id,
                alert.timestamp,
                alert.type,
                alert.state,
                alert.value,
                alert.unit,
                int(time.time()),
            ),
        )
        db.touch_device(conn, alert.device_id)
        event_id = cursor.fetchone()["id"]

    await manager.broadcast({"type": "alert", "data": serialize_alert(alert, event_id)})
    return {"id": event_id, "status": "stored"}


@router.post("/api/v1/alerts/anomaly")
async def post_anomaly(alert: AnomalyIn, response: Response):
    event = store_anomaly(alert)
    if event is not None:
        await manager.broadcast({"type": "alert", "data": event})
        response.status_code = 201
        return {"id": event["id"], "status": "stored"}
    response.status_code = 200
    return {"id": None, "status": "unchanged"}


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


@router.get("/api/v1/alerts")
def get_alerts(limit: int = Query(50, ge=1, le=1000)):
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM events ORDER BY ts DESC LIMIT %s", (limit,)
        ).fetchall()

    return {
        "items": [
            {
                "id": row["id"],
                "type": row["type"],
                "severity": SEVERITY_BY_STATE.get(row["state"], "info"),
                "event": "cleared" if row["state"] == "OK" else "raised",
                "source": row["device_id"],
                "received_at": iso_timestamp(row["received_at"]),
                "acknowledged": False,
                "value": row["value"],
                "unit": row["unit"],
                "details": row.get("details"),
            }
            for row in rows
        ]
    }