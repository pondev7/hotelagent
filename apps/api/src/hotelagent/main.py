"""FastAPI application entrypoint.

Slice 0 deliberately exposes one route. Module routers are mounted here as each
module lands; this file stays a wiring file and never grows business logic.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from hotelagent.config import get_settings

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
    """Liveness probe. Deliberately checks nothing downstream — readiness against
    Postgres and Redis arrives with the database session in the next slice."""
    return {"status": "ok", "env": settings.env}
