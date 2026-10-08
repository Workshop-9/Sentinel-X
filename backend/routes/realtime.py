from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from ..video import CameraUnavailable, camera_stream
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
    try:
        camera_stream.start()
    except CameraUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    return StreamingResponse(
        camera_stream.iter_mjpeg(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )

@router.get("/health")
def health():
    return {"ok": True}