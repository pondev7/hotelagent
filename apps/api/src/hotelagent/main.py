"""FastAPI application entrypoint.

Module routers are mounted here as each module lands; this file stays a wiring
file and never grows business logic.
"""

from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from hotelagent.config import get_settings
from hotelagent.db import registry as _registry  # noqa: F401  (populates Base.metadata)
from hotelagent.db.session import get_session
from hotelagent.errors import install_error_handlers
from hotelagent.logging import configure_logging
from hotelagent.modules.channel.router import router as channel_router
from hotelagent.modules.conversation.router import router as conversation_router
from hotelagent.modules.inventory.router import cities_router
from hotelagent.modules.inventory.router import router as inventory_router
from hotelagent.modules.ops.router import router as ops_router

settings = get_settings()

configure_logging(json_output=settings.log_json)


def _operation_id(route: APIRoute) -> str:
    """Name each operation after its endpoint function.

    FastAPI's default appends the path and the method —
    `list_hotels_api_hotels_get` — which generates a TypeScript client nobody
    wants to call and renames every function the day a route moves. The endpoint
    name is stable, readable, and makes a rename visible in the diff.

    Uniqueness is then our problem rather than FastAPI's, which is why
    `tests/unit/test_openapi_contract.py` asserts it.
    """
    return route.name


app = FastAPI(
    title="HotelAgent API",
    version="0.1.0",
    generate_unique_id_function=_operation_id,
)

# Before the routers, so no route can be registered without them.
install_error_handlers(app)

app.include_router(channel_router)
app.include_router(cities_router)
app.include_router(inventory_router)
app.include_router(conversation_router)
app.include_router(ops_router)

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
