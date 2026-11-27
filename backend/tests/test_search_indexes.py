"""Full-text and trigram indexes used by retrieval v2."""

from uuid import UUID

from sqlalchemy import select, text

from app.models.story_models import Chapter, Story, StoryChunk


def _vector() -> list[float]:
    values = [0.0] * 768
    values[0] = 1.0
    return values


async def test_chunk_text_search_is_generated_and_matches_proper_nouns(user_client, session):
    me = (await user_client.get("/me")).json()
    story = Story(owner_id=UUID(me["id"]), title="Search")
    session.add(story)
    await session.flush()
    chapter = Chapter(
        story_id=story.id,
        chapter_number=1,
        position=1024.0,
        title="One",
        content="Mira Voss carried the lantern.",
        word_count=6,
        revision=1,
        index_status="indexed",
    )
    session.add(chapter)
    await session.flush()
    session.add(
        StoryChunk(
            story_id=story.id,
            chapter_id=chapter.id,
            chapter_number=1,
            scene_index=0,
            chunk_index=0,
            chunk_kind="scene",
            text="Mira Voss carried the lantern.",
            token_count=6,
            start_line=1,
            end_line=1,
            entities=[],
            content_hash="a" * 64,
            embedding=_vector(),
            embedding_model="nomic-embed-text",
        )
    )
    await session.commit()

    match = await session.scalar(
        select(StoryChunk.id).where(
            StoryChunk.story_id == story.id,
            text("text_search @@ websearch_to_tsquery('simple', :q)").bindparams(q="Voss"),
        )
    )
    assert match is not None

    indexes = set(
        (await session.execute(text("SELECT indexname FROM pg_indexes"))).scalars()
    )
    assert {
        "ix_story_chunks_fts",
        "ix_story_chunks_embedding_hnsw",
        "ix_entities_name_trgm",
        "ix_entity_aliases_alias_trgm",
    } <= indexes
    extension = await session.scalar(
        text("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'")
    )
    assert extension == 1
