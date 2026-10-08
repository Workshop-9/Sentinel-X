import secrets

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from ..security import API_KEY
from ..ws import manager

router = APIRouter(tags=["Realtime"])

KEY_PREFIX = "api-key."

def _has_valid_key(protocols: list[str]) -> bool:
    """Comparaison en temps constant de la clé offerte via Sec-WebSocket-Protocol."""
    if not API_KEY:
        return False
    expected = API_KEY.encode()
    return any(
        p.startswith(KEY_PREFIX)
        and secrets.compare_digest(p[len(KEY_PREFIX):].encode(), expected)
        for p in protocols
    )

@router.websocket("/ws")
@router.websocket("/ws/live")
async def ws_endpoint(websocket: WebSocket):
    if not _has_valid_key(websocket.scope.get("subprotocols", [])):
        await websocket.close(code=1008)
        return

    await websocket.accept(subprotocol="sentinel-x")
    await manager.connect(websocket, accepted=True)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        # Nettoyage garanti, quelle que soit la cause de la fermeture
        manager.disconnect(websocket)


@router.get("/video")
@router.get("/video/stream")
def video():
    raise HTTPException(status_code=501, detail="Video stream is not implemented yet")


@router.get("/health")
def health():
    return {"ok": True}