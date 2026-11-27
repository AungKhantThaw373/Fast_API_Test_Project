"""AI usage ledger and usage API."""

from uuid import UUID

import pytest

from app.models.story_models import Story
from app.models.wiki_models import AIUsage
from app.services import ai_usage


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
    story = Story(owner_id=owner_id, title="Usage")
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
    assert body["calls"] == 2
    assert "budget_usd" not in body
