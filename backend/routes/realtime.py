from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

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
def video():
    raise HTTPException(status_code=501, detail="Video stream is not implemented yet")

@router.get("/health")
def health():
    return {"ok": True}