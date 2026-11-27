"""Ask Story refuses without evidence and validates every citation quote."""

from uuid import UUID

import pytest
from fastapi import HTTPException

from app.models.story_models import Chapter, Story, StoryChunk
from app.services import ask_story


def _vector() -> list[float]:
    values = [0.0] * 768
    values[0] = 1.0
    return values


async def _fixture(user_client, session):
    me = (await user_client.get("/me")).json()
    owner_id = UUID(me["id"])
    story = Story(owner_id=owner_id, title="Ask", external_analysis_enabled=True)
    session.add(story)
    await session.flush()
    chapter = Chapter(
        story_id=story.id,
        chapter_number=1,
        position=1024.0,
        title="The gate",
        content="Mira crossed the yard at dawn. The gate was locked.",
        word_count=11,
        revision=1,
        index_status="indexed",
    )
    session.add(chapter)
    await session.flush()
    chunk = StoryChunk(
        story_id=story.id,
        chapter_id=chapter.id,
        chapter_number=1,
        scene_index=0,
        chunk_index=0,
        text="Mira crossed the yard at dawn. The gate was locked.",
        start_line=1,
        end_line=1,
        content_hash="a" * 64,
        embedding=_vector(),
        embedding_model="nomic-embed-text",
    )
    session.add(chunk)
    await session.commit()
    return owner_id, story, chunk


async def test_answer_keeps_only_exact_citations(user_client, session, monkeypatch):
    owner_id, story, chunk = await _fixture(user_client, session)
    monkeypatch.setattr(ask_story, "embed_queries", lambda _texts: [_vector()])

    async def fake_call(*_args, **_kwargs):
        return {
            "answer": "Mira crossed the yard at dawn.",
            "unsure": False,
            "citations": [
                {
                    "chunk_id": str(chunk.id),
                    "quote": "Mira crossed the yard at dawn.",
                    "explanation": "Direct statement.",
                },
                {
                    "chunk_id": str(chunk.id),
                    "quote": "Mira crossed the yard at noon.",
                    "explanation": "Fabricated wording.",
                },
            ],
        }

    monkeypatch.setattr(ask_story, "structured_ai_json", fake_call)
    result = await ask_story.ask_story(session, story, owner_id, "When did Mira cross?")
    assert result["unsure"] is False
    assert len(result["citations"]) == 1
    assert result["citations"][0]["line"] == 1
    assert result["citations"][0]["quote"] == "Mira crossed the yard at dawn."


async def test_fabricated_citation_becomes_a_refusal(user_client, session, monkeypatch):
    owner_id, story, chunk = await _fixture(user_client, session)
    monkeypatch.setattr(ask_story, "embed_queries", lambda _texts: [_vector()])

    async def fake_call(*_args, **_kwargs):
        return {
            "answer": "The gate was open.",
            "unsure": False,
            "citations": [
                {"chunk_id": str(chunk.id), "quote": "The gate was open.", "explanation": "Wrong."}
            ],
        }

    monkeypatch.setattr(ask_story, "structured_ai_json", fake_call)
    result = await ask_story.ask_story(session, story, owner_id, "Was the gate open?")
    assert result["unsure"] is True
    assert result["citations"] == []


async def test_no_indexed_evidence_does_not_call_the_model(user_client, session, monkeypatch):
    me = (await user_client.get("/me")).json()
    owner_id = UUID(me["id"])
    story = Story(owner_id=owner_id, title="Empty")
    session.add(story)
    await session.commit()
    monkeypatch.setattr(ask_story, "embed_queries", lambda _texts: [_vector()])
    called = False

    async def fake_call(*_args, **_kwargs):
        nonlocal called
        called = True
        return {"answer": "x", "unsure": False, "citations": []}

    monkeypatch.setattr(ask_story, "structured_ai_json", fake_call)
    result = await ask_story.ask_story(session, story, owner_id, "Who is Mira?")
    assert result["unsure"] is True
    assert called is False


async def test_embedding_failure_is_a_readable_503(user_client, session, monkeypatch):
    owner_id, story, _chunk = await _fixture(user_client, session)

    def unavailable(_texts):
        raise ConnectionError("Ollama is not running")

    monkeypatch.setattr(ask_story, "embed_queries", unavailable)
    with pytest.raises(HTTPException) as raised:
        await ask_story.ask_story(session, story, owner_id, "When did Mira cross?")
    assert raised.value.status_code == 503
    assert "Ollama" in raised.value.detail


async def test_ask_api_requires_ownership(user_client, session):
    me = (await user_client.get("/me")).json()
    owner_id = UUID(me["id"])
    story = Story(owner_id=owner_id, title="Mine")
    session.add(story)
    await session.commit()
    response = await user_client.post(f"/stories/{story.id}/ask", json={"question": "Who?"})
    assert response.status_code == 200
    assert response.json()["unsure"] is True
