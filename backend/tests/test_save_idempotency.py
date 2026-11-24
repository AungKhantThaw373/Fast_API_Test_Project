import uuid


async def _chapter(client, content="First draft."):
    story = (await client.post("/stories", json={"title": "Idempotency"})).json()
    chapter = (
        await client.post(
            f"/stories/{story['id']}/chapters",
            json={"title": "Chapter one", "content": content},
        )
    ).json()
    return story, chapter


async def test_the_same_save_id_does_not_increment_twice(user_client):
    _story, chapter = await _chapter(user_client)
    save_id = str(uuid.uuid4())
    body = {
        "content": "Second draft.",
        "expected_revision": chapter["revision"],
        "client_save_id": save_id,
    }

    first = await user_client.put(f"/stories/chapters/{chapter['id']}", json=body)
    assert first.status_code == 200
    assert first.json()["revision"] == 2

    replay = await user_client.put(f"/stories/chapters/{chapter['id']}", json=body)
    assert replay.status_code == 200
    assert replay.json()["revision"] == 2


async def test_a_new_save_id_increments_again(user_client):
    _story, chapter = await _chapter(user_client)
    first = await user_client.put(
        f"/stories/chapters/{chapter['id']}",
        json={
            "content": "Second draft.",
            "expected_revision": 1,
            "client_save_id": str(uuid.uuid4()),
        },
    )
    second = await user_client.put(
        f"/stories/chapters/{chapter['id']}",
        json={
            "content": "Third draft.",
            "expected_revision": first.json()["revision"],
            "client_save_id": str(uuid.uuid4()),
        },
    )
    assert second.status_code == 200
    assert second.json()["revision"] == 3


async def test_conflict_response_carries_the_current_revision_and_text(user_client):
    _story, chapter = await _chapter(user_client)
    await user_client.put(
        f"/stories/chapters/{chapter['id']}",
        json={"content": "Saved by the other tab.", "expected_revision": 1},
    )

    conflict = await user_client.put(
        f"/stories/chapters/{chapter['id']}",
        json={"content": "My local text.", "expected_revision": 1},
    )
    assert conflict.status_code == 409
    body = conflict.json()
    assert body["current_revision"] == 2
    assert body["current_content"] == "Saved by the other tab."
    assert "changed since it was loaded" in body["detail"]


async def test_keep_mine_saves_against_the_current_revision(user_client):
    _story, chapter = await _chapter(user_client)
    await user_client.put(
        f"/stories/chapters/{chapter['id']}",
        json={"content": "Other tab text.", "expected_revision": 1},
    )
    conflict = await user_client.put(
        f"/stories/chapters/{chapter['id']}",
        json={"content": "My local text.", "expected_revision": 1},
    )
    current_revision = conflict.json()["current_revision"]

    keep_mine = await user_client.put(
        f"/stories/chapters/{chapter['id']}",
        json={
            "content": "My local text.",
            "expected_revision": current_revision,
            "client_save_id": str(uuid.uuid4()),
        },
    )
    assert keep_mine.status_code == 200
    assert keep_mine.json()["content"] == "My local text."
    assert keep_mine.json()["revision"] == current_revision + 1
