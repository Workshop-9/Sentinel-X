from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from .. import db
from ..models import TelemetryIn
from ..ws import manager
from .formatters import iso_timestamp

router = APIRouter(tags=["Telemetry"])


@router.post("/api/v1/telemetry", status_code=201)
async def post_telemetry(telemetry: TelemetryIn):
    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO telemetry(device_id, ts, temperature, gas, humidity, motion, label) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s)",
            (
                telemetry.device_id,
                telemetry.timestamp,
                telemetry.temperature,
                telemetry.gas,
                telemetry.humidity,
                telemetry.motion,
                telemetry.label,
            ),
        )
        db.touch_device(conn, telemetry.device_id)

    await manager.broadcast(
        {
            "type": "telemetry",
            "data": {
                "received_at": iso_timestamp(telemetry.timestamp),
                "sensors": {
                    "temperature_c": telemetry.temperature,
                    "gas_ppm": telemetry.gas,
                    "humidity_pct": telemetry.humidity,
                    "motion": telemetry.motion,
                },
                "label": telemetry.label,
            },
        }
    )
    return {"status": "stored"}


@router.get("/api/v1/telemetry")
def get_telemetry(
    limit: int = Query(200, ge=1, le=2000),
    since: Optional[str] = None,
):
    query = "SELECT * FROM telemetry"
    params = []
    if since:
        try:
            since_timestamp = int(
                datetime.fromisoformat(since.replace("Z", "+00:00")).timestamp()
            )
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
                    "motion": row["motion"],
                },
                "label": row["label"],
            }
            for row in reversed(rows)
        ]
    }