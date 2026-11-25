"""Chapter indexing uses sentence chunks and reuses unchanged embeddings."""

from uuid import UUID

from sqlalchemy import select

from app.models.story_models import Chapter, SceneEmbedding, Story, StoryChunk
from app.models.wiki_models import Entity, EntityAlias, EntityMention
from app.services import indexing


def _vector(seed: int) -> list[float]:
    values = [0.0] * 768
    values[seed % 768] = 1.0
    return values


async def test_reindex_writes_chunks_mentions_and_reuses_vectors(
    user_client, session, monkeypatch
):
    me = (await user_client.get("/me")).json()
    owner_id = UUID(me["id"])
    story = Story(owner_id=owner_id, title="Chunked", external_analysis_enabled=False)
    session.add(story)
    await session.flush()
    entity = Entity(
        story_id=story.id,
        entity_type="character",
        name="Mira",
        canonical_name="mira",
        summary="",
    )
    session.add(entity)
    await session.flush()
    entity_id = entity.id
    session.add(
        EntityAlias(
            entity_id=entity_id,
            alias="Mira",
            normalized_alias="mira",
        )
    )
    content = "\n\n".join(
        f"Mira crossed the yard on night {index}. The lantern threw a long shadow."
        for index in range(80)
    )
    chapter = Chapter(
        story_id=story.id,
        chapter_number=1,
        position=1024.0,
        title="Night",
        content=content,
        word_count=len(content.split()),
        revision=1,
        index_status="pending",
    )
    session.add(chapter)
    await session.commit()
    chapter_id = chapter.id

    calls: list[list[str]] = []

    def fake_embed(texts: list[str]) -> list[list[float]]:
        calls.append(list(texts))
        return [_vector(index + 1) for index, _text in enumerate(texts)]

    monkeypatch.setattr(indexing, "embed_texts", fake_embed)

    assert await indexing.reindex_chapter(chapter_id) == "done"
    session.expire_all()
    chunks = list(
        await session.scalars(
            select(StoryChunk)
            .where(StoryChunk.chapter_id == chapter_id)
            .order_by(StoryChunk.chunk_index)
        )
    )
    assert len(chunks) >= 2
    assert all(chunk.entities == [entity_id] for chunk in chunks)
    assert all(chunk.token_count > 0 for chunk in chunks)
    assert all("Mira crossed" in chunk.text for chunk in chunks)
    mentions = list(
        await session.scalars(
            select(EntityMention).where(EntityMention.chapter_id == chapter_id)
        )
    )
    assert mentions
    legacy = list(
        await session.scalars(
            select(SceneEmbedding).where(SceneEmbedding.chapter_id == chapter_id)
        )
    )
    assert len(legacy) == len(chunks)

    first_embedded = len(calls[0])
    assert await indexing.reindex_chapter(chapter_id) == "done"
    assert calls[-1] == []
    assert first_embedded > 0
    session.expire_all()
    again = list(
        await session.scalars(
            select(StoryChunk).where(StoryChunk.chapter_id == chapter_id)
        )
    )
    assert len(again) == len(chunks)
