"""Story search endpoint: ownership, filters, and score breakdown."""

from uuid import UUID

from app.models.story_models import Chapter, Story, StoryChunk
from app.models.wiki_models import Entity
from app.services import retrieval


def _vector() -> list[float]:
    values = [0.0] * 768
    values[0] = 1.0
    return values


async def _seed(user_client, session):
    me = (await user_client.get("/me")).json()
    story = Story(owner_id=UUID(me["id"]), title="Search API")
    session.add(story)
    await session.flush()
    mira = Entity(
        story_id=story.id, entity_type="character", name="Mira Voss", canonical_name="mira voss"
    )
    session.add(mira)
    await session.flush()
    first = Chapter(
        story_id=story.id,
        chapter_number=1,
        position=1024.0,
        title="The Lantern",
        content="Mira Voss carried the lantern through the rain.",
        word_count=8,
        revision=1,
        index_status="indexed",
    )
    second = Chapter(
        story_id=story.id,
        chapter_number=2,
        position=2048.0,
        title="The Gate",
        content="Kael waited by the gate and watched the road.",
        word_count=9,
        revision=1,
        index_status="indexed",
    )
    session.add_all([first, second])
    await session.flush()
    session.add_all(
        [
            StoryChunk(
                story_id=story.id,
                chapter_id=first.id,
                chapter_number=1,
                scene_index=0,
                chunk_index=0,
                chunk_kind="scene",
                text="Mira Voss carried the lantern through the rain.",
                token_count=8,
                start_line=1,
                end_line=1,
                entities=[mira.id],
                content_hash="a" * 64,
                embedding=_vector(),
                embedding_model="nomic-embed-text",
            ),
            StoryChunk(
                story_id=story.id,
                chapter_id=second.id,
                chapter_number=2,
                scene_index=0,
                chunk_index=0,
                chunk_kind="scene",
                text="Kael waited by the gate and watched the road.",
                token_count=9,
                start_line=1,
                end_line=1,
                entities=[],
                content_hash="b" * 64,
                embedding=_vector(),
                embedding_model="nomic-embed-text",
            ),
        ]
    )
    await session.commit()
    retrieval.CACHE._data.clear()
    return story, mira


async def test_search_returns_chips_breakdown_and_filters(user_client, session, monkeypatch):
    story, mira = await _seed(user_client, session)
    monkeypatch.setattr(retrieval, "embed_queries", lambda texts: [_vector() for _text in texts])
    response = await user_client.get(f"/stories/{story.id}/search", params={"q": "lantern"})
    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "lantern"
    assert body["results"]
    first = body["results"][0]
    assert first["chapter_number"] == 1
    assert first["chapter_title"] == "The Lantern"
    assert first["start_line"] == 1
    assert "lexical" in first["scores"]
    assert first["entities"] == [
        {"id": str(mira.id), "name": "Mira Voss", "entity_type": "character"}
    ]

    filtered = await user_client.get(
        f"/stories/{story.id}/search", params={"q": "lantern", "chapter_min": 2}
    )
    assert filtered.status_code == 200
    assert all(item["chapter_number"] >= 2 for item in filtered.json()["results"])

    by_entity = await user_client.get(
        f"/stories/{story.id}/search", params={"q": "lantern", "entity_id": str(mira.id)}
    )
    assert by_entity.status_code == 200
    assert [item["chapter_number"] for item in by_entity.json()["results"]] == [1]


async def test_search_is_owned_and_validates_query(user_client, session, make_client, monkeypatch):
    story, _mira = await _seed(user_client, session)
    monkeypatch.setattr(retrieval, "embed_queries", lambda texts: [_vector() for _text in texts])
    other = await make_client("other", "other@example.com")
    assert (await other.get(f"/stories/{story.id}/search", params={"q": "lantern"})).status_code == 404
    assert (await user_client.get(f"/stories/{story.id}/search", params={"q": "x"})).status_code == 422
