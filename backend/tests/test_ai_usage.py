"""AI usage ledger, budget guard, and usage API."""

from uuid import UUID

import pytest
from fastapi import HTTPException

from app.models.story_models import Story
from app.models.wiki_models import AIUsage
from app.services import ai_usage
from app.services.ai_settings import AIConfig


def cloud_config() -> AIConfig:
    return AIConfig(
        provider="openrouter",
        model="gpt-4o-mini",
        api_key="test",
        base_url="http://example.invalid",
        protocol="openai",
    )


def test_local_calls_are_free_and_cloud_calls_are_priced():
    assert ai_usage.estimate_cost("ollama", "qwen3:4b-instruct", 100_000, 10_000) == 0
    cloud = ai_usage.estimate_cost("openrouter", "gpt-4o-mini", 1_000_000, 1_000_000)
    assert float(cloud) == pytest.approx(0.75)
    inputs, outputs = ai_usage.estimate_scan_tokens(40_000)
    assert inputs == 10_000
    assert outputs == 1200


async def test_usage_summary_groups_by_purpose(user_client, session):
    me = (await user_client.get("/me")).json()
    owner_id = UUID(me["id"])
    story = Story(owner_id=owner_id, title="Budget", monthly_ai_budget=5)
    session.add(story)
    await session.flush()
    session.add_all(
        [
            AIUsage(
                user_id=owner_id,
                story_id=story.id,
                purpose="continuity",
                provider="ollama",
                model="qwen3:4b-instruct",
                input_tokens=100,
                output_tokens=20,
                cost_estimate=0,
                duration_ms=1500,
            ),
            AIUsage(
                user_id=owner_id,
                story_id=story.id,
                purpose="continuity",
                provider="ollama",
                model="qwen3:4b-instruct",
                input_tokens=50,
                output_tokens=10,
                cost_estimate=0,
                duration_ms=500,
            ),
        ]
    )
    await session.commit()

    summary = await ai_usage.usage_summary(session, story.id)
    assert summary["calls"] == 2
    assert summary["input_tokens"] == 150
    assert summary["spent_usd"] == 0
    assert summary["by_purpose"][0]["purpose"] == "continuity"
    assert summary["by_purpose"][0]["average_duration_ms"] == 1000

    response = await user_client.get(f"/stories/{story.id}/ai-usage")
    assert response.status_code == 200
    body = response.json()
    assert body["budget_usd"] == 5
    assert body["calls"] == 2


async def test_cloud_scan_is_refused_without_a_budget(user_client, session, monkeypatch):
    me = (await user_client.get("/me")).json()
    owner_id = UUID(me["id"])
    story = Story(owner_id=owner_id, title="Local only", monthly_ai_budget=0)
    session.add(story)
    await session.commit()

    async def fake_config(_user_id):
        return cloud_config()

    monkeypatch.setattr(ai_usage, "load_ai_config", fake_config)
    with pytest.raises(HTTPException) as raised:
        await ai_usage.check_budget(
            session, story, owner_id, chars=40_000, purpose="Continuity scan"
        )
    assert raised.value.status_code == 402
    assert "local-only" in raised.value.detail


async def test_local_provider_is_allowed_with_zero_budget(user_client, session, monkeypatch):
    me = (await user_client.get("/me")).json()
    owner_id = UUID(me["id"])
    story = Story(owner_id=owner_id, title="Offline first", monthly_ai_budget=0)
    session.add(story)
    await session.commit()

    async def local_config(_user_id):
        return AIConfig(
            provider="ollama",
            model="qwen3:4b-instruct",
            api_key="",
            base_url="http://127.0.0.1:11434",
            protocol="ollama",
        )

    monkeypatch.setattr(ai_usage, "load_ai_config", local_config)
    budget = await ai_usage.check_budget(
        session, story, owner_id, chars=200_000, purpose="Continuity scan"
    )
    assert budget["estimated_cost_usd"] == 0
    assert budget["budget_usd"] == 0
