"""Pagination cursors, ETags, and the single-query story list."""

from sqlalchemy import event

from app.db import engine


async def _story(client, title: str) -> dict:
    response = await client.post("/stories", json={"title": title})
    assert response.status_code == 201
    return response.json()


async def _walk(client, url: str, key: str) -> list[dict]:
    items: list[dict] = []
    cursor = None
    for _ in range(20):
        separator = "&" if "?" in url else "?"
        page_url = url if cursor is None else f"{url}{separator}cursor={cursor}"
        response = await client.get(page_url)
        assert response.status_code == 200, response.text
        body = response.json()
        items.extend(body[key])
        cursor = body.get("next_cursor")
        if not cursor:
            return items
    raise AssertionError("cursor did not terminate")


async def test_story_list_pages_without_duplicates(user_client):
    created = [await _story(user_client, f"Story {index}") for index in range(5)]

    first = (await user_client.get("/stories?limit=2")).json()
    assert len(first["stories"]) == 2
    assert first["next_cursor"]

    everything = await _walk(user_client, "/stories?limit=2", "stories")
    ids = [item["id"] for item in everything]
    assert len(ids) == len(set(ids)) == 5
    # Newest first, and every created story is present.
    assert ids[0] == created[-1]["id"]
    assert set(ids) == {story["id"] for story in created}


async def test_story_list_ignores_a_bad_cursor(user_client):
    await _story(user_client, "Only story")
    response = await user_client.get("/stories?cursor=not-a-cursor")
    assert response.status_code == 400


async def test_story_list_is_one_aggregate_query(user_client):
    for index in range(3):
        story = await _story(user_client, f"Story {index}")
        for chapter in range(2):
            await user_client.post(
                f"/stories/{story['id']}/chapters",
                json={"title": f"Chapter {chapter}", "content": "one two three"},
            )

    statements: list[str] = []

    def record(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", record)
    try:
        response = await user_client.get("/stories")
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record)

    assert response.status_code == 200
    assert len(response.json()["stories"]) == 3
    story_queries = [item for item in statements if "FROM stories" in item]
    assert len(story_queries) == 1, statements
    assert "count(" in story_queries[0].lower()
    assert "sum(" in story_queries[0].lower()


async def test_bible_list_pages_in_its_display_order(user_client):
    story = await _story(user_client, "Bible")
    names = ["Zephyr", "Anvil", "Mira", "Brontide", "Calyx"]
    for index, name in enumerate(names):
        response = await user_client.post(
            f"/stories/{story['id']}/bible",
            json={
                "category": "character",
                "name": name,
                "description": f"Entry {index}",
                "details": {},
            },
        )
        assert response.status_code == 201

    pages = await _walk(user_client, f"/stories/{story['id']}/bible?limit=2", "entries")
    assert [item["name"] for item in pages] == sorted(names)
    assert len({item["id"] for item in pages}) == 5


async def test_story_detail_caps_the_chapter_list(user_client, monkeypatch):
    from app.routes import stories as story_routes

    monkeypatch.setattr(story_routes, "CHAPTER_LIST_CAP", 1)
    story = await _story(user_client, "Long")
    for index in range(3):
        await user_client.post(
            f"/stories/{story['id']}/chapters",
            json={"title": f"Chapter {index}", "content": "text"},
        )

    detail = (await user_client.get(f"/stories/{story['id']}")).json()
    assert detail["chapter_count"] == 3
    assert len(detail["chapters"]) == 1
    assert detail["chapters_truncated"] is True


async def test_chapter_etag_returns_304_until_the_next_save(user_client):
    story = await _story(user_client, "ETag")
    chapter = (
        await user_client.post(
            f"/stories/{story['id']}/chapters",
            json={"title": "One", "content": "first draft"},
        )
    ).json()

    first = await user_client.get(f"/stories/chapters/{chapter['id']}")
    etag = first.headers["etag"]
    assert etag

    not_modified = await user_client.get(
        f"/stories/chapters/{chapter['id']}", headers={"If-None-Match": etag}
    )
    assert not_modified.status_code == 304
    assert not_modified.content == b""

    saved = await user_client.put(
        f"/stories/chapters/{chapter['id']}",
        json={"content": "second draft", "expected_revision": chapter["revision"]},
    )
    assert saved.status_code == 200

    updated = await user_client.get(f"/stories/chapters/{chapter['id']}")
    assert updated.headers["etag"] != etag

    refreshed = await user_client.get(
        f"/stories/chapters/{chapter['id']}", headers={"If-None-Match": etag}
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["content"] == "second draft"
