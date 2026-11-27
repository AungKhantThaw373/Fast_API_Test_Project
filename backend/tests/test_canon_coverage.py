"""Lazy canon coverage: per-arc counts, current arc, and scoped extraction."""

from sqlalchemy import update

from app.models.story_models import Chapter


async def _story(client) -> str:
    response = await client.post("/stories", json={"title": "Lazy canon"})
    assert response.status_code == 201
    return response.json()["id"]


async def _chapter(client, story_id: str, number: int) -> dict:
    response = await client.post(
        f"/stories/{story_id}/chapters",
        json={"title": f"Chapter {number}", "content": f"Chapter {number} has words."},
    )
    assert response.status_code == 201
    return response.json()


async def _arc(client, story_id: str, name: str) -> str:
    response = await client.post(f"/stories/{story_id}/arcs", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


async def test_coverage_tracks_current_revision_and_current_arc(user_client, session):
    story_id = await _story(user_client)
    chapters = [await _chapter(user_client, story_id, number) for number in range(1, 4)]
    early = await _arc(user_client, story_id, "Early")
    late = await _arc(user_client, story_id, "Late")
    await user_client.put(
        f"/stories/{story_id}/arcs",
        json={"arc_id": early, "chapter_ids": [chapters[0]["id"], chapters[1]["id"]]},
    )
    await user_client.put(
        f"/stories/{story_id}/arcs",
        json={"arc_id": late, "chapter_ids": [chapters[2]["id"]]},
    )

    await session.execute(
        update(Chapter)
        .where(Chapter.chapter_number == 1, Chapter.story_id == story_id)
        .values(bible_scan_revision=Chapter.revision)
    )
    await session.commit()

    response = await user_client.get(f"/stories/{story_id}/canon/coverage")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["chapters"] == 3
    assert body["extracted"] == 1
    assert body["pending"] == 2
    assert body["unassigned_chapters"] == 0
    assert body["current_arc_id"] == late
    by_name = {arc["arc_name"]: arc for arc in body["arcs"]}
    assert by_name["Early"]["chapter_count"] == 2
    assert by_name["Early"]["extracted_count"] == 1
    assert by_name["Early"]["pending_count"] == 1
    assert by_name["Early"]["complete"] is False
    assert by_name["Late"]["extracted_count"] == 0


async def test_extract_only_queues_the_selected_arc(user_client):
    story_id = await _story(user_client)
    chapters = [await _chapter(user_client, story_id, number) for number in range(1, 3)]
    arc = await _arc(user_client, story_id, "Only this one")
    await user_client.put(
        f"/stories/{story_id}/arcs",
        json={"arc_id": arc, "chapter_ids": [chapters[0]["id"]]},
    )

    response = await user_client.post(f"/stories/{story_id}/canon/arcs/{arc}/extract")
    assert response.status_code == 202, response.text
    assert response.json() == {
        "arc_id": arc,
        "scheduled_count": 1,
        "skipped_count": 0,
        "chapter_count": 1,
    }

    foreign = "00000000-0000-0000-0000-000000000000"
    assert (await user_client.post(f"/stories/{story_id}/canon/arcs/{foreign}/extract")).status_code == 404


async def test_canon_coverage_is_owner_scoped(user_client, make_client):
    story_id = await _story(user_client)
    arc = await _arc(user_client, story_id, "Mine")
    other = await make_client("mallory", "mallory@example.com")

    assert (await other.get(f"/stories/{story_id}/canon/coverage")).status_code == 404
    assert (await other.post(f"/stories/{story_id}/canon/arcs/{arc}/extract")).status_code == 404