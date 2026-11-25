"""Retrieval v2: RRF, entity-first context, budget, and cache behaviour."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select

from app.models.story_models import Chapter, Story
from app.models.wiki_models import (
    Entity,
    EntityAlias,
    EntityFact,
    EntityRelationship,
    StoryThread,
)
from app.services import indexing, retrieval


def _vector(seed: int) -> list[float]:
    values = [0.0] * 768
    values[seed % 768] = 1.0
    return values


async def _seed(user_client, session, monkeypatch):
    me = (await user_client.get("/me")).json()
    story = Story(owner_id=UUID(me["id"]), title="Retrieval", external_analysis_enabled=False)
    session.add(story)
    await session.flush()
    mira = Entity(
        story_id=story.id, entity_type="character", name="Mira Voss", canonical_name="mira voss"
    )
    kael = Entity(
        story_id=story.id, entity_type="character", name="Kael", canonical_name="kael"
    )
    session.add_all([mira, kael])
    await session.flush()
    session.add_all(
        [
            EntityAlias(entity_id=mira.id, alias="Mira", normalized_alias="mira"),
            EntityAlias(
                entity_id=mira.id, alias="the captain", normalized_alias="the captain"
            ),
            EntityAlias(entity_id=kael.id, alias="Kael", normalized_alias="kael"),
        ]
    )
    first = Chapter(
        story_id=story.id,
        chapter_number=1,
        position=1024.0,
        title="The lantern",
        content="Mira Voss carried the lantern. Her grey eyes searched the yard.\n\nKael waited by the gate.",
        word_count=17,
        revision=1,
        index_status="pending",
    )
    second = Chapter(
        story_id=story.id,
        chapter_number=2,
        position=2048.0,
        title="After",
        content="Kael spoke to the captain about the broken watch. The rain did not stop.",
        word_count=14,
        revision=1,
        index_status="pending",
    )
    session.add_all([first, second])
    await session.commit()
    first_id, second_id = first.id, second.id
    session.add_all(
        [
            EntityFact(
                entity_id=mira.id,
                predicate="eye_color",
                value_text="grey",
                quote="Her grey eyes searched the yard.",
                status="accepted",
                chapter_id=first_id,
                valid_from_chapter=1,
            ),
            EntityFact(
                entity_id=mira.id,
                predicate="status",
                value_text="alive",
                quote="Mira Voss carried the lantern.",
                status="accepted",
                chapter_id=first_id,
                valid_from_chapter=1,
            ),
            EntityRelationship(
                story_id=story.id,
                from_entity_id=mira.id,
                to_entity_id=kael.id,
                relationship_type="sibling_of",
                since_chapter=1,
                status="accepted",
            ),
            StoryThread(
                story_id=story.id,
                title="Who betrayed the Night Watch?",
                state="open",
                setup_chapter_id=first_id,
                linked_entity_ids=[mira.id],
            ),
        ]
    )
    await session.commit()

    def fake_embed(texts: list[str]) -> list[list[float]]:
        return [_vector(index + 1) for index, _text in enumerate(texts)]

    monkeypatch.setattr(indexing, "embed_texts", fake_embed)
    monkeypatch.setattr(retrieval, "embed_queries", lambda texts: [_vector(1) for _text in texts])
    assert await indexing.reindex_chapter(first_id) == "done"
    assert await indexing.reindex_chapter(second_id) == "done"
    return story, mira, kael, first_id


def test_rrf_is_deterministic_and_prefers_agreement():
    first, second, third = uuid4(), uuid4(), uuid4()
    fused = retrieval.reciprocal_rank_fusion([[first, second], [second, third]])
    assert [item for item, _score in fused] == [second, first, third]
    assert fused[0][1] > fused[1][1] > fused[2][1]
    for _ in range(20):
        assert retrieval.reciprocal_rank_fusion([[first, second], [second, third]]) == fused


async def test_alias_retrieves_entity_facts_and_old_context(user_client, session, monkeypatch):
    story, mira, _kael, first_id = await _seed(user_client, session, monkeypatch)
    result = await retrieval.retrieve_for_scene(
        session,
        story.id,
        "The captain looked at the lantern.",
        current_chapter=500,
        use_cache=False,
    )
    assert mira.id in result.context.entity_ids
    assert "eye_color: grey" in result.context.text
    assert "sibling_of" in result.context.text
    assert "Who betrayed the Night Watch?" in result.context.text
    assert "APPEARANCES" in result.context.text
    assert result.context.token_count <= retrieval.DEFAULT_CONTEXT_TOKENS
    assert result.chunks
    assert result.chunks[0].chapter_number >= 1


async def test_context_budget_is_hard_and_quotes_are_whole(user_client, session, monkeypatch):
    story, mira, _kael, first_id = await _seed(user_client, session, monkeypatch)
    for index in range(120):
        session.add(
            EntityFact(
                entity_id=mira.id,
                predicate=f"detail_{index}",
                value_text="x" * 80,
                quote=("A complete sentence about Mira. " * 80).strip(),
                status="accepted",
                chapter_id=first_id,
                valid_from_chapter=1,
            )
        )
    await session.commit()
    context = await retrieval.build_entity_context(
        session, story.id, [mira.id], budget_tokens=260
    )
    assert context.token_count <= 260
    assert context.text.startswith("ENTITIES PRESENT")
    for line in context.text.splitlines():
        if line.startswith("- ") and '"' in line:
            assert line.endswith('"')


async def test_search_cache_hits_and_invalidates_on_fact_change(user_client, session, monkeypatch):
    story, mira, _kael, first_id = await _seed(user_client, session, monkeypatch)
    retrieval.CACHE._data.clear()
    calls: list[int] = []

    def counted(texts: list[str]) -> list[list[float]]:
        calls.append(1)
        return [_vector(1) for _text in texts]

    monkeypatch.setattr(retrieval, "embed_queries", counted)
    first = await retrieval.search_chunks(session, story.id, "lantern", limit=5)
    second = await retrieval.search_chunks(session, story.id, "lantern", limit=5)
    assert len(calls) == 1
    assert second.cache_hit is True
    assert first.chunks

    fact = await session.scalar(select(EntityFact).where(EntityFact.entity_id == mira.id))
    assert fact is not None
    fact.updated_at = datetime.now(UTC) + timedelta(seconds=2)
    await session.commit()
    await retrieval.search_chunks(session, story.id, "lantern", limit=5)
    assert len(calls) == 2
