"""Incremental scene extraction: hashes, quotes, duplicates, conflicts."""

import pytest
from sqlalchemy import select

from app.db import async_session
from app.models.story_models import Chapter
from app.models.wiki_models import Entity, EntityFact, SceneMeta
from app.services import extraction


async def _seed(client):
    story = (await client.post("/stories", json={"title": "Extraction"})).json()
    chapter = (await client.post(
        f"/stories/{story['id']}/chapters",
        json={
            "chapter_number": 1,
            "title": "Eyes",
            "content": (
                "Mira Voss had grey eyes.\nShe waited.\n\n***\n\n"
                "Mira Voss had green eyes.\nShe waited.\n"
            ),
        },
    )).json()
    entity = (await client.post(
        f"/stories/{story['id']}/entities",
        json={"name": "Mira Voss", "entity_type": "character"},
    )).json()
    accepted = (await client.post(
        f"/entities/{entity['id']}/facts",
        json={
            "predicate": "eye_color",
            "value_text": "grey",
            "quote": "Mira Voss had grey eyes.",
            "chapter_id": chapter["id"],
        },
    )).json()
    return story, chapter, entity, accepted


def _result(scene_text: str) -> dict:
    if "green eyes" in scene_text:
        return {
            "facts": [
                {
                    "entity_name": "Mira Voss",
                    "predicate": "eye_color",
                    "value": "green",
                    "quote": "Mira Voss had green eyes.",
                    "confidence": 92,
                },
                {
                    "entity_name": "Mira Voss",
                    "predicate": "eye_color",
                    "value": "green",
                    "quote": "Mira Voss had green eyes.",
                    "confidence": 92,
                },
            ],
            "entities": [
                {
                    "name": "Kale",
                    "entity_type": "character",
                    "summary": "A watcher in the yard.",
                    "quote": "She waited.",
                    "confidence": 80,
                }
            ],
            "relationships": [],
            "threads": [],
            "events": [],
        }
    return {
        "facts": [
            {
                "entity_name": "Mira Voss",
                "predicate": "eye_color",
                "value": "grey",
                "quote": "Mira Voss had grey eyes.",
                "confidence": 95,
            },
            {
                "entity_name": "Mira Voss",
                "predicate": "eye_color",
                "value": "blue",
                "quote": "Mira Voss had blue eyes.",
                "confidence": 95,
            },
        ],
        "entities": [],
        "relationships": [],
        "threads": [],
        "events": [],
    }


@pytest.mark.asyncio
async def test_incremental_extraction_skips_unchanged_scenes(user_client, monkeypatch):
    story, chapter, _entity, accepted = await _seed(user_client)
    calls: list[str] = []

    async def fake(system, user, owner_id, **kwargs):
        user_text = str(user)
        calls.append(user_text)
        scene = user_text.split("<scene>\n", 1)[1].split("\n</scene>", 1)[0]
        return _result(scene)

    monkeypatch.setattr(extraction, "structured_ai_json", fake)
    async with async_session() as session:
        row = await session.scalar(select(Chapter).where(Chapter.id == chapter["id"]))
        assert row is not None
        owner = row.story_id
        stats = await extraction.extract_chapter(session, row, owner)
        await session.commit()
    assert stats.model_calls == 2
    assert stats.scenes_skipped == 0
    assert stats.facts == 1
    assert stats.entities == 1
    assert stats.conflicts == 1
    assert stats.rejected == 1

    async with async_session() as session:
        facts = list(await session.scalars(select(EntityFact).where(EntityFact.status != "rejected")))
        accepted_row = next(fact for fact in facts if fact.status == "accepted")
        proposed = next(fact for fact in facts if fact.status == "proposed")
        assert accepted_row.value_text == "grey"
        assert proposed.value_text == "green"
        assert proposed.supersedes_id == accepted_row.id
        assert proposed.quote is not None
        assert proposed.quote in row.content
        assert await session.scalar(select(Entity).where(Entity.name == "Kale")) is not None
        metas = list(await session.scalars(select(SceneMeta).where(SceneMeta.chapter_id == row.id)))
        assert len(metas) == 2
        assert all(meta.last_extracted_hash for meta in metas)
        assert all(meta.last_extracted_at for meta in metas)

    calls.clear()
    async with async_session() as session:
        row = await session.scalar(select(Chapter).where(Chapter.id == chapter["id"]))
        assert row is not None
        stats = await extraction.extract_chapter(session, row, row.story_id)
        await session.commit()
    assert calls == []
    assert stats.model_calls == 0
    assert stats.scenes_skipped == 2


@pytest.mark.asyncio
async def test_changed_scene_is_the_only_one_re_extracted(user_client, monkeypatch):
    _story, chapter, _entity, _accepted = await _seed(user_client)
    calls = 0

    async def fake(system, user, owner_id, **kwargs):
        nonlocal calls
        calls += 1
        return {"facts": [], "entities": [], "relationships": [], "threads": [], "events": []}

    monkeypatch.setattr(extraction, "structured_ai_json", fake)
    async with async_session() as session:
        row = await session.scalar(select(Chapter).where(Chapter.id == chapter["id"]))
        assert row is not None
        await extraction.extract_chapter(session, row, row.story_id)
        await session.commit()
    assert calls == 2

    async with async_session() as session:
        row = await session.scalar(select(Chapter).where(Chapter.id == chapter["id"]))
        assert row is not None
        row.content = row.content.replace("She waited.\n", "She waited, then left.\n", 1)
        await session.commit()
    calls = 0
    async with async_session() as session:
        row = await session.scalar(select(Chapter).where(Chapter.id == chapter["id"]))
        assert row is not None
        stats = await extraction.extract_chapter(session, row, row.story_id)
        await session.commit()
    assert calls == 1
    assert stats.model_calls == 1
    assert stats.scenes_skipped == 1
