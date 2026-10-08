import logging
import os
from collections.abc import AsyncIterator

import httpx
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

AI_VIDEO_URL = os.getenv("SENTINEL_AI_VIDEO_URL", "http://127.0.0.1:8081/video")
AI_VIDEO_TOKEN = os.getenv("SENTINEL_AI_VIDEO_TOKEN", "")
CONNECT_TIMEOUT_S = 5.0


async def video_stream() -> StreamingResponse:
    headers: dict[str, str] = {}
    if AI_VIDEO_TOKEN:
        headers["Authorization"] = f"Bearer {AI_VIDEO_TOKEN}"

    client = httpx.AsyncClient(
        timeout=httpx.Timeout(connect=CONNECT_TIMEOUT_S, read=None, write=5.0, pool=5.0)
    )
    try:
        request = client.build_request("GET", AI_VIDEO_URL, headers=headers)
        response = await client.send(request, stream=True)
    except httpx.HTTPError as error:
        await client.aclose()
        logger.warning("Flux vidéo IA indisponible : %s", error)
        raise HTTPException(
            status_code=503,
            detail="Le service vidéo IA est indisponible.",
        ) from error

    content_type = response.headers.get("content-type", "")
    if response.status_code != 200:
        status_code = 503 if response.status_code == 503 else 502
        await response.aclose()
        await client.aclose()
        raise HTTPException(
            status_code=status_code,
            detail=f"Le service vidéo IA a répondu avec le statut {response.status_code}.",
        )
    if not content_type.lower().startswith("multipart/x-mixed-replace"):
        await response.aclose()
        await client.aclose()
        raise HTTPException(
            status_code=502,
            detail="Le service IA n’a pas retourné un flux vidéo MJPEG.",
        )

    async def relay() -> AsyncIterator[bytes]:
        try:
            async for chunk in response.aiter_raw():
                if chunk:
                    yield chunk
        except httpx.HTTPError:
            logger.exception("La connexion au flux vidéo IA a été interrompue.")
        finally:
            await response.aclose()
            await client.aclose()

    return StreamingResponse(
        relay(),
        media_type=content_type,
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
        },
    )
