import asyncio

import httpx

import main
from llm import chain
from models.schemas import AnalysisResponse, StructuredAnalysis


def test_temporary_analysis_uses_client_history_without_persisting(monkeypatch):
    calls = []

    async def fake_pipeline(**kwargs):
        calls.append(kwargs)
        return AnalysisResponse(
            query=kwargs["query"],
            analysis=StructuredAnalysis(general_analysis="Temporary response."),
            model_used="test-model",
        )

    async def exercise_requests():
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/analyze/temporary", json={
                "query": "What should I do next?",
                "conversation_history": [
                    {"role": "user", "content": "My landlord changed the locks."},
                    {"role": "assistant", "content": "That may raise tenant protection issues."},
                ],
            })
            assert response.status_code == 200
            assert response.json()["analysis"]["general_analysis"] == "Temporary response."

            too_many_turns = await client.post("/api/analyze/temporary", json={
                "query": "What now?",
                "conversation_history": [{"role": "user", "content": "Earlier question."}] * 21,
            })
            assert too_many_turns.status_code == 422

    monkeypatch.setattr(chain, "run_analysis_pipeline", fake_pipeline)
    asyncio.run(exercise_requests())

    assert len(calls) == 1
    assert calls[0]["query"] == "What should I do next?"
    assert calls[0]["conversation_history"] == [
        {"role": "user", "content": "My landlord changed the locks."},
        {"role": "assistant", "content": "That may raise tenant protection issues."},
    ]
    assert calls[0]["ephemeral_context"] is None
