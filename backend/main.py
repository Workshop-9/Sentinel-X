from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import db
from .routes.commands import router as commands_router
from .routes.dashboard import router as dashboard_router
from .routes.ingestion import router as ingestion_router
from .routes.realtime import router as realtime_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    try:
        yield
    finally:
        db.close_db()


app = FastAPI(title="SENTINEL-X API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingestion_router)
app.include_router(dashboard_router)
app.include_router(commands_router)
app.include_router(realtime_router)