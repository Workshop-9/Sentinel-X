import asyncio
from contextlib import asynccontextmanager
import os

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import db
from .mqtt_bridge import mqtt_bridge
from .security import require_api_key, validate_api_key_config
from .routes.alerts import router as alerts_router
from .routes.commands import router as commands_router
from .routes.status import router as dashboard_router
from .routes.realtime import router as realtime_router
from .routes.telemetry import router as telemetry_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_api_key_config()
    db.init_db()
    try:
        mqtt_bridge.start(asyncio.get_running_loop())
        yield
    finally:
        mqtt_bridge.stop()
        db.close_db()


app = FastAPI(title="SENTINEL-X API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(alerts_router, dependencies=[Depends(require_api_key)])
app.include_router(telemetry_router, dependencies=[Depends(require_api_key)])
app.include_router(dashboard_router, dependencies=[Depends(require_api_key)])
app.include_router(commands_router, dependencies=[Depends(require_api_key)])
app.include_router(realtime_router)