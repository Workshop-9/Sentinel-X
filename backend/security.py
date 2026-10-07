import os
import secrets
from pathlib import Path

from dotenv import load_dotenv
from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

load_dotenv(Path(__file__).with_name(".env"))
API_KEY = os.getenv("API_KEY", "")
api_key_header = APIKeyHeader(name="X-API-Key", scheme_name="ApiKeyAuth", auto_error=False)


def validate_api_key_config():
    if len(API_KEY) < 32 or not API_KEY.isascii():
        raise RuntimeError("API_KEY must be configured with at least 32 ASCII characters")


def require_api_key(x_api_key: str | None = Security(api_key_header)):
    if not API_KEY:
        raise HTTPException(status_code=503, detail="API authentication is not configured")
    if not x_api_key or not secrets.compare_digest(x_api_key, API_KEY):
        raise HTTPException(status_code=401, detail="Invalid API key")