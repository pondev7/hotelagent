"""The health route is the whole of slice 0's behaviour, so it is the whole of
slice 0's test surface. Unit tests need no running services."""

import httpx

from hotelagent.main import app


async def test_health_reports_ok() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "env": "local"}
