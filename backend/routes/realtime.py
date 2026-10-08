from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..video import video_stream
from ..ws import manager

router = APIRouter(tags=["Realtime"])

@router.websocket("/ws")
@router.websocket("/ws/live")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    await manager.connect(websocket, accepted=True)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)


@router.get("/video")
@router.get("/video/stream")
async def video():
    return await video_stream()

@router.get("/health")
def health():
    return {"ok": True}