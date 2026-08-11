"""Readiness reports on the database, so it needs a real one."""

import httpx
import pytest

from hotelagent.main import app


@pytest.mark.usefixtures("test_database_url")
async def test_ready_reports_database_ok() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}


async def test_liveness_does_not_depend_on_the_database() -> None:
    """Liveness must answer even when everything downstream is broken — that is
    the entire point of separating it from readiness."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
