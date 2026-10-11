import asyncio

import httpx

import main
from llm import chain
from models.schemas import AnalysisResponse, StructuredAnalysis


def test_test_api_route_requires_configured_token_and_calls_pipeline(monkeypatch):
    calls = []

    async def fake_pipeline(**kwargs):
        calls.append(kwargs)
        return AnalysisResponse(
            query=kwargs["query"],
            analysis=StructuredAnalysis(general_analysis="Test response."),
            model_used="test-model",
        )

    async def exercise_requests():
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            disabled = await client.post("/__test/analyze", json={"query": "explain bns 77"})
            assert disabled.status_code == 404

            monkeypatch.setenv("TRANA_TEST_API_TOKEN", "t" * 40)
            rejected = await client.post(
                "/__test/analyze",
                json={"query": "explain bns 77"},
                headers={"X-Test-Token": "wrong-token"},
            )
            assert rejected.status_code == 404

            accepted = await client.post(
                "/__test/analyze",
                json={"query": "explain bns 77"},
                headers={"X-Test-Token": "t" * 40},
            )
            assert accepted.status_code == 200
            assert accepted.json()["analysis"]["general_analysis"] == "Test response."

    monkeypatch.delenv("TRANA_TEST_API_TOKEN", raising=False)
    monkeypatch.setattr(chain, "run_analysis_pipeline", fake_pipeline)
    asyncio.run(exercise_requests())

    assert len(calls) == 1
    assert calls[0]["query"] == "explain bns 77"
