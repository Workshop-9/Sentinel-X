from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import db
from .routes.alerts import router as alerts_router
from .routes.commands import router as commands_router
from .routes.status import router as dashboard_router
from .routes.realtime import router as realtime_router
from .routes.telemetry import router as telemetry_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield
    db.close_db()


app = FastAPI(title="SENTINEL-X API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(alerts_router)
app.include_router(telemetry_router)
app.include_router(dashboard_router)
app.include_router(commands_router)
app.include_router(realtime_router)