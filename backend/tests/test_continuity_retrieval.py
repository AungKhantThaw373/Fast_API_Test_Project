"""Batch continuity retrieval: one vector query, not one per scene."""

from uuid import UUID

from sqlalchemy import event

from app.db import engine
from app.models.story_models import Chapter, SceneEmbedding, Story
from app.services import continuity


def _vector(seed: int) -> list[float]:
    values = [0.0] * 768
    values[seed % 768] = 1.0
    return values


async def test_scan_retrieves_all_scenes_in_one_vector_query(
    user_client, session, monkeypatch
):
    me = (await user_client.get("/me")).json()
    owner_id = UUID(me["id"])

    story = Story(owner_id=owner_id, title="Batch", external_analysis_enabled=True)
    session.add(story)
    await session.flush()

    earlier = Chapter(
        story_id=story.id,
        chapter_number=1,
        position=1024.0,
        title="Earlier",
        content="Mira crossed the yard.\n\n***\n\nThe gate was locked.",
        word_count=12,
        revision=1,
        index_status="indexed",
    )
    session.add(earlier)
    await session.flush()
    for index in range(3):
        session.add(
            SceneEmbedding(
                story_id=story.id,
                chapter_id=earlier.id,
                chapter_number=1,
                chunk_index=index,
                text=f"Earlier scene {index}",
                start_line=index + 1,
                end_line=index + 2,
                chunk_metadata={},
                embedding=_vector(index),
            )
        )

    draft = Chapter(
        story_id=story.id,
        chapter_number=2,
        position=2048.0,
        title="Draft",
        content="Kael waited.\n\n***\n\nA horn sounded.\n\n***\n\nNobody answered him.",
        word_count=12,
        revision=1,
        index_status="indexed",
    )
    session.add(draft)
    await session.commit()

    monkeypatch.setattr(
        continuity, "embed_queries", lambda texts: [_vector(0) for _text in texts]
    )

    async def fake_provider(*_args, **_kwargs):
        return {"findings": []}

    monkeypatch.setattr(continuity, "structured_ai_json", fake_provider)

    statements: list[str] = []

    def record(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", record)
    try:
        findings = await continuity.scan_chapter(session, story.id, draft, owner_id)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record)

    assert findings == []
    vector_queries = [item for item in statements if "jsonb_array_elements_text" in item]
    assert len(vector_queries) == 1, statements
    assert "LATERAL" in vector_queries[0]
    # Vector search, one evidence load, one story-settings read, the canon
    # exception list, and three deterministic-context reads - a fixed count,
    # independent of the number of scenes.
    assert len(statements) <= 8, statements


async def test_scan_is_incremental_per_scene_and_reports_progress(
    user_client, session, monkeypatch
):
    me = (await user_client.get("/me")).json()
    owner_id = UUID(me["id"])
    story = Story(owner_id=owner_id, title="Incremental", external_analysis_enabled=True)
    session.add(story)
    await session.flush()
    earlier = Chapter(
        story_id=story.id,
        chapter_number=1,
        position=1024.0,
        title="Earlier",
        content="Mira crossed the yard.",
        word_count=4,
        revision=1,
        index_status="indexed",
    )
    session.add(earlier)
    await session.flush()
    session.add(
        SceneEmbedding(
            story_id=story.id,
            chapter_id=earlier.id,
            chapter_number=1,
            chunk_index=0,
            text="Mira crossed the yard.",
            start_line=1,
            end_line=1,
            chunk_metadata={},
            embedding=_vector(0),
        )
    )
    draft = Chapter(
        story_id=story.id,
        chapter_number=2,
        position=2048.0,
        title="Draft",
        content="Kael waited.\n\n***\n\nA horn sounded.\n\n***\n\nNobody answered him.",
        word_count=9,
        revision=1,
        index_status="indexed",
    )
    session.add(draft)
    await session.commit()
    monkeypatch.setattr(
        continuity, "embed_queries", lambda texts: [_vector(0) for _text in texts]
    )
    prompts: list[str] = []

    async def fake_provider(_system, prompt, *_args, **_kwargs):
        prompts.append(prompt)
        return {"findings": []}

    monkeypatch.setattr(continuity, "structured_ai_json", fake_provider)
    progress: list[dict[str, int]] = []

    async def report(data: dict[str, int]) -> None:
        progress.append(data)

    findings = await continuity.scan_chapter(
        session, story.id, draft, owner_id, on_progress=report
    )
    assert findings == []
    assert len(prompts) == 3
    assert [item["scenes_done"] for item in progress] == [1, 2, 3]
    assert {item["scenes_total"] for item in progress} == {3}


async def test_evidence_is_deduplicated_and_ordered_by_distance(
    user_client, session
):
    me = (await user_client.get("/me")).json()
    owner_id = UUID(me["id"])
    story = Story(owner_id=owner_id, title="Distance", external_analysis_enabled=True)
    session.add(story)
    await session.flush()
    earlier = Chapter(
        story_id=story.id,
        chapter_number=1,
        position=1024.0,
        title="Earlier",
        content="text",
        word_count=1,
        revision=1,
        index_status="indexed",
    )
    session.add(earlier)
    await session.flush()
    for index in range(4):
        session.add(
            SceneEmbedding(
                story_id=story.id,
                chapter_id=earlier.id,
                chapter_number=1,
                chunk_index=index,
                text=f"Evidence {index}",
                start_line=index + 1,
                end_line=index + 2,
                chunk_metadata={},
                embedding=_vector(index),
            )
        )
    await session.commit()

    # Two query scenes that both prefer the same evidence row.
    evidence = await continuity.retrieve_evidence(
        session, story.id, 2, [_vector(1), _vector(1)], top_k=2
    )
    assert evidence
    assert len(evidence) == len(set(evidence))
    ordered = list(evidence.values())
    assert ordered[0].chunk_index == 1
