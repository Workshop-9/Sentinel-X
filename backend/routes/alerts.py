import time
from typing import Optional

from fastapi import APIRouter, Query

from .. import db
from ..models import AlertIn
from ..ws import manager
from .formatters import iso_timestamp, serialize_alert

router = APIRouter(tags=["Alerts"])


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