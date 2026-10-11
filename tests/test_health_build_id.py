import asyncio

import httpx

import main


def test_health_reports_deployment_commit_id(monkeypatch):
    monkeypatch.setenv("RENDER_GIT_COMMIT", "render-sha-123")
    monkeypatch.setenv("GIT_COMMIT", "generic-sha-456")

    async def request_health():
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
        assert response.status_code == 200
        return response.json()

    payload = asyncio.run(request_health())

    assert payload["build_id"] == "render-sha-123"
    assert payload["status"] == "healthy"


def test_health_uses_safe_build_id_fallback(monkeypatch):
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    monkeypatch.delenv("GIT_COMMIT", raising=False)
    monkeypatch.delenv("SOURCE_VERSION", raising=False)

    async def request_health():
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
        assert response.status_code == 200
        return response.json()

    assert asyncio.run(request_health())["build_id"] == "unknown"
