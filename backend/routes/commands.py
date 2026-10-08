import time

from fastapi import APIRouter, Query

from .. import db
from ..models import CommandIn
from ..ws import manager

router = APIRouter(tags=["Commands"])


@router.post("/api/v1/commands", status_code=201)
async def post_command(command: CommandIn):
    with db.get_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO commands(device_id, target, action, duration_ms, created_at) "
            "VALUES(%s,%s,%s,%s,%s) RETURNING id",
            (command.device_id, command.target, command.action,
             command.duration_ms, int(time.time())),
        )
        command_id = cursor.fetchone()["id"]

    sent = mqtt_bridge.publish_command(command.device_id, {
        "id": command_id,
        "target": command.target,
        "action": command.action,
        "duration_ms": command.duration_ms,
    })
    if sent:
        with db.get_conn() as conn:
            conn.execute("UPDATE commands SET delivered=TRUE WHERE id=%s", (command_id,))

    status = "sent" if sent else "queued"
    await manager.broadcast({
        "type": "command",
        "data": {"id": command_id, **command.model_dump(), "status": status},
    })
    return {"id": command_id, "status": status}


@router.get("/api/v1/commands/pending")
def pending_commands(device_id: str = Query(...)):
    """The ESP polls this endpoint every 1-2 seconds."""
    with db.get_conn() as conn:
        db.touch_device(conn, device_id)
        rows = conn.execute(
            "SELECT id, target, action, duration_ms FROM commands "
            "WHERE device_id=%s AND delivered=FALSE ORDER BY id",
            (device_id,),
        ).fetchall()
        if rows:
            ids = [row["id"] for row in rows]
            placeholders = ",".join("%s" for _ in ids)
            conn.execute(
                f"UPDATE commands SET delivered=TRUE WHERE id IN ({placeholders})",
                ids,
            )
    return {"commands": [dict(row) for row in rows]}