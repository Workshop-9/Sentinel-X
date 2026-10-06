import time

from fastapi import APIRouter

from .. import db
from ..models import AlertIn, TelemetryIn
from ..ws import manager
from .formatters import iso_timestamp, serialize_alert

router = APIRouter(tags=["Ingestion"])


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


@router.post("/api/v1/telemetry", status_code=201)
async def post_telemetry(telemetry: TelemetryIn):
    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO telemetry(device_id, ts, temperature, gas, humidity) "
            "VALUES(%s,%s,%s,%s,%s)",
            (
                telemetry.device_id,
                telemetry.timestamp,
                telemetry.temperature,
                telemetry.gas,
                telemetry.humidity,
            ),
        )
        db.touch_device(conn, telemetry.device_id)

    await manager.broadcast({
        "type": "telemetry",
        "data": {
            "received_at": iso_timestamp(telemetry.timestamp),
            "sensors": {
                "temperature_c": telemetry.temperature,
                "gas_ppm": telemetry.gas,
                "humidity_pct": telemetry.humidity,
            },
        },
    })
    return {"status": "stored"}