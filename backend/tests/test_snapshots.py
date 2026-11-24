from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select

from app.models.story_models import ChapterRevision
from app.services.snapshots import apply_retention, content_hash


async def _chapter(client, story_id, title, content):
    return (
        await client.post(
            f"/stories/{story_id}/chapters", json={"title": title, "content": content}
        )
    ).json()


@pytest.fixture
async def story_with_chapter(user_client):
    story = (await user_client.post("/stories", json={"title": "History"})).json()
    chapter = await _chapter(user_client, story["id"], "One", "The first version of the text.")
    return story, chapter


async def test_first_edit_stores_the_previous_text(user_client, story_with_chapter, session):
    _story, chapter = story_with_chapter
    await user_client.put(
        f"/stories/chapters/{chapter['id']}",
        json={"content": "The second version of the text.", "expected_revision": 1},
    )

    revisions = (
        await session.scalars(
            select(ChapterRevision).where(ChapterRevision.chapter_id == UUID(chapter["id"]))
        )
    ).all()
    assert len(revisions) == 1
    assert revisions[0].revision_number == 1
    assert revisions[0].content == "The first version of the text."
    assert revisions[0].kind == "autosave"
    assert revisions[0].content_hash == content_hash("The first version of the text.")
    assert revisions[0].char_count == len("The first version of the text.")


async def test_the_same_revision_is_never_snapshotted_twice(
    user_client, story_with_chapter, session
):
    _story, chapter = story_with_chapter
    for content in ("Second.", "Third."):
        await user_client.put(
            f"/stories/chapters/{chapter['id']}",
            json={
                "content": content,
                "expected_revision": (
                    await user_client.get(f"/stories/chapters/{chapter['id']}")
                ).json()["revision"],
            },
        )

    revision_numbers = [
        item.revision_number
        for item in await session.scalars(
            select(ChapterRevision).where(ChapterRevision.chapter_id == UUID(chapter["id"]))
        )
    ]
    assert len(revision_numbers) == len(set(revision_numbers))


async def test_checkpoint_endpoint_pins_the_current_revision(user_client, story_with_chapter):
    _story, chapter = story_with_chapter
    response = await user_client.post(
        f"/stories/chapters/{chapter['id']}/checkpoint", json={"label": "Before the rewrite"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["kind"] == "checkpoint"
    assert body["revision_number"] == 1

    listed = (await user_client.get(f"/stories/chapters/{chapter['id']}/revisions")).json()
    assert listed["revisions"][0]["kind"] == "checkpoint"


async def test_diff_returns_hunks_without_the_whole_chapter(user_client, story_with_chapter):
    _story, chapter = story_with_chapter
    await user_client.put(
        f"/stories/chapters/{chapter['id']}",
        json={"content": "The second version of the text.", "expected_revision": 1},
    )
    # Pin revision 2 so there is a second version to diff against.
    assert (
        await user_client.post(f"/stories/chapters/{chapter['id']}/checkpoint", json={})
    ).status_code == 201

    diff = await user_client.get(
        f"/stories/chapters/{chapter['id']}/revisions/1/diff/2"
    )
    assert diff.status_code == 200
    body = diff.json()
    assert body["older"]["revision_number"] == 1
    assert body["newer"]["revision_number"] == 2
    assert body["hunks"]
    lines = "\n".join("\n".join(hunk["lines"]) for hunk in body["hunks"])
    assert "-The first version of the text." in lines
    assert "+The second version of the text." in lines
    # Hunks only: the unchanged body is not echoed back in full.
    assert "content" not in body


async def test_diff_of_unknown_versions_is_404(user_client, story_with_chapter):
    _story, chapter = story_with_chapter
    response = await user_client.get(f"/stories/chapters/{chapter['id']}/revisions/1/diff/9")
    assert response.status_code == 404


async def test_restore_pins_the_pre_restore_draft(
    user_client, story_with_chapter, session
):
    _story, chapter = story_with_chapter
    await user_client.put(
        f"/stories/chapters/{chapter['id']}",
        json={"content": "The draft I will lose.", "expected_revision": 1},
    )
    restored = await user_client.post(
        f"/stories/chapters/{chapter['id']}/revisions/1/restore"
    )
    assert restored.status_code == 200
    assert restored.json()["content"] == "The first version of the text."

    kinds = {
        item.kind
        for item in await session.scalars(
            select(ChapterRevision).where(ChapterRevision.chapter_id == UUID(chapter["id"]))
        )
    }
    assert "restore" in kinds


async def test_retention_prunes_old_autosaves_but_keeps_checkpoints(
    user_client, story_with_chapter, session
):
    _story, chapter = story_with_chapter
    chapter_id = UUID(chapter["id"])
    now = datetime.now(UTC)

    def make_revision(number: int, age_days: float, kind: str) -> ChapterRevision:
        created = now - timedelta(days=age_days)
        return ChapterRevision(
            id=__import__("uuid").uuid4(),
            chapter_id=chapter_id,
            revision_number=number,
            title="Old",
            content=f"content {number}",
            word_count=2,
            kind=kind,
            content_hash=content_hash(f"content {number}"),
            char_count=len(f"content {number}"),
            created_at=created,
        )

    session.add_all(
        [
            make_revision(100, 0.1, "autosave"),   # inside the 48h window
            make_revision(101, 10, "autosave"),    # 7-day window: one per hour
            make_revision(102, 10.01, "autosave"), # same hour bucket: dropped
            make_revision(103, 60, "autosave"),    # 90-day window: one per day
            make_revision(104, 60.01, "autosave"), # same day bucket: dropped
            make_revision(105, 400, "autosave"),   # past 90 days: dropped
            make_revision(106, 400, "checkpoint"), # checkpoints are forever
        ]
    )
    await session.commit()

    dropped = await apply_retention(session, chapter_id)
    await session.commit()

    remaining = {
        item.revision_number
        for item in await session.scalars(
            select(ChapterRevision).where(ChapterRevision.chapter_id == chapter_id)
        )
    }
    assert dropped >= 3
    assert {100, 101, 103, 106} <= remaining
    assert 105 not in remaining
    assert 104 not in remaining or 103 not in remaining
