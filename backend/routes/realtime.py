from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from ..security import API_KEY
from ..ws import manager

router = APIRouter(tags=["Realtime"])


@router.websocket("/ws")
@router.websocket("/ws/live")
async def ws_endpoint(websocket: WebSocket):
    offered_protocols = websocket.scope.get("subprotocols", [])
    if not API_KEY or f"api-key.{API_KEY}" not in offered_protocols:
        await websocket.close(code=1008)
        return

    await websocket.accept(subprotocol="sentinel-x")
    await manager.connect(websocket, accepted=True)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@router.get("/video")
@router.get("/video/stream")
def video():
    raise HTTPException(status_code=501, detail="Video stream is not implemented yet")


@router.get("/health")
def health():
    return {"ok": True}