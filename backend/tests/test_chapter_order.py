import time
import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.models.story_models import Chapter


async def _story(client, title="Positions"):
    return (await client.post("/stories", json={"title": title})).json()


async def _chapters(client, story_id, count=3):
    created = []
    for index in range(count):
        response = await client.post(
            f"/stories/{story_id}/chapters",
            json={"title": f"Chapter {index + 1}", "content": f"Body {index + 1}"},
        )
        assert response.status_code == 201
        created.append(response.json())
    return created


async def test_new_chapters_append_with_increasing_positions(user_client, session):
    story = await _story(user_client)
    chapters = await _chapters(user_client, story["id"], 3)

    rows = {
        row.id: row.position
        for row in await session.scalars(
            select(Chapter).where(Chapter.story_id == uuid.UUID(story["id"]))
        )
    }
    positions = [rows[uuid.UUID(chapter["id"])] for chapter in chapters]
    assert positions == sorted(positions)
    assert len(set(positions)) == 3
    # Display numbers are contiguous from 1.
    assert [chapter["chapter_number"] for chapter in chapters] == [1, 2, 3]


async def test_reorder_rewrites_positions_and_display_numbers(user_client, session):
    story = await _story(user_client)
    chapters = await _chapters(user_client, story["id"])
    reversed_ids = [chapter["id"] for chapter in reversed(chapters)]

    response = await user_client.put(
        f"/stories/{story['id']}/chapters/order", json={"chapter_ids": reversed_ids}
    )
    assert response.status_code == 200
    assert [row["chapter_number"] for row in response.json()["chapters"]] == [1, 2, 3]

    rows = {
        str(row.id): row.position
        for row in await session.scalars(
            select(Chapter).where(Chapter.story_id == uuid.UUID(story["id"]))
        )
    }
    positions = [rows[chapter_id] for chapter_id in reversed_ids]
    assert positions == sorted(positions)
    assert len(set(positions)) == 3

    reopened = (await user_client.get(f"/stories/{story['id']}")).json()
    assert [chapter["id"] for chapter in reopened["chapters"]] == reversed_ids


async def test_new_chapter_after_reorder_goes_to_the_end(user_client):
    story = await _story(user_client)
    chapters = await _chapters(user_client, story["id"])
    reordered = [chapters[1]["id"], chapters[2]["id"], chapters[0]["id"]]
    await user_client.put(
        f"/stories/{story['id']}/chapters/order", json={"chapter_ids": reordered}
    )

    added = (
        await user_client.post(
            f"/stories/{story['id']}/chapters",
            json={"title": "New last", "content": "Ending."},
        )
    ).json()
    assert added["chapter_number"] == 4
    assert added["id"] not in reordered


async def test_delete_keeps_display_numbers_contiguous(user_client):
    story = await _story(user_client)
    chapters = await _chapters(user_client, story["id"], 4)
    deleted = await user_client.delete(f"/stories/chapters/{chapters[1]['id']}")
    assert deleted.status_code == 200
    numbers = [row["chapter_number"] for row in deleted.json()["chapters"]]
    assert numbers == [1, 2, 3]
    reopened = (await user_client.get(f"/stories/{story['id']}")).json()
    assert [chapter["chapter_number"] for chapter in reopened["chapters"]] == [1, 2, 3]


async def test_move_between_stories_keeps_both_orders_valid(user_client, session):
    source = await _story(user_client, "Source")
    destination = await _story(user_client, "Destination")
    source_chapters = await _chapters(user_client, source["id"], 3)
    destination_chapters = await _chapters(user_client, destination["id"], 2)

    moved = await user_client.post(
        f"/stories/chapters/{source_chapters[1]['id']}/move",
        json={"destination_story_id": destination["id"]},
    )
    assert moved.status_code == 200
    assert moved.json()["chapter"]["chapter_number"] == 3

    source_after = (await user_client.get(f"/stories/{source['id']}")).json()
    destination_after = (await user_client.get(f"/stories/{destination['id']}")).json()
    assert [chapter["chapter_number"] for chapter in source_after["chapters"]] == [1, 2]
    assert [chapter["chapter_number"] for chapter in destination_after["chapters"]] == [1, 2, 3]
    assert [chapter["id"] for chapter in destination_after["chapters"]][:2] == [
        chapter["id"] for chapter in destination_chapters
    ]


async def test_reorder_is_fast_with_many_chapters(user_client, session):
    story = await _story(user_client, "Large")
    story_id = uuid.UUID(story["id"])
    now = datetime.now(UTC)
    chapters = [
        Chapter(
            id=uuid.uuid4(),
            story_id=story_id,
            chapter_number=index + 1,
            position=(index + 1) * 1024.0,
            title=f"Chapter {index + 1}",
            content="body",
            word_count=1,
            revision=1,
            index_status="pending",
            created_at=now,
            updated_at=now,
        )
        for index in range(1100)
    ]
    session.add_all(chapters)
    await session.commit()

    ids = [str(chapter.id) for chapter in chapters]
    shuffled = ids[::-1]
    started = time.perf_counter()
    response = await user_client.put(
        f"/stories/{story['id']}/chapters/order", json={"chapter_ids": shuffled}
    )
    elapsed = time.perf_counter() - started
    assert response.status_code == 200
    assert elapsed < 5.0, f"reorder of 1,100 chapters took {elapsed:.2f}s"
