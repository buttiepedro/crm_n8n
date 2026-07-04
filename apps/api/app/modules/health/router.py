"""Health checks: liveness (proceso vivo) y readiness (DB accesible)."""

import sqlalchemy as sa
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.db.session import get_sessionmaker

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def liveness() -> dict:
    return {"status": "ok"}


@router.get("/ready")
async def readiness() -> JSONResponse:
    try:
        async with get_sessionmaker()() as session:
            await session.execute(sa.text("SELECT 1"))
    except Exception:
        return JSONResponse(status_code=503, content={"status": "unavailable", "db": "down"})
    return JSONResponse(content={"status": "ready"})
