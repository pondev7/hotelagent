"""FastAPI application entrypoint.

Module routers are mounted here as each module lands; this file stays a wiring
file and never grows business logic.
"""

from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from hotelagent.config import get_settings
from hotelagent.db.session import get_session

settings = get_settings()

app = FastAPI(
    title="HotelAgent API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness: is the process running at all?

    Deliberately checks nothing downstream. An orchestrator restarts a
    container that fails liveness, and restarting the API does not fix a
    database outage — it just adds a restart loop to an incident.
    """
    return {"status": "ok", "env": settings.env}


@app.get("/health/ready")
async def ready(session: Annotated[AsyncSession, Depends(get_session)]) -> JSONResponse:
    """Readiness: can this process actually serve traffic?

    Distinct from liveness because the correct responses differ — a failing
    readiness check should remove the instance from the load balancer, not
    restart it.
    """
    try:
        await session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "database": type(exc).__name__},
        )
    return JSONResponse(status_code=200, content={"status": "ready", "database": "ok"})
