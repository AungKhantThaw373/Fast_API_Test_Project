async def _story_and_chapter(client):
    story = (await client.post("/stories", json={"title": "Conflict story"})).json()
    chapter = (
        await client.post(
            f"/stories/{story['id']}/chapters",
            json={"title": "Chapter one", "content": "First draft."},
        )
    ).json()
    return story, chapter


async def test_stale_revision_returns_409(user_client):
    _story, chapter = await _story_and_chapter(user_client)

    first = await user_client.put(
        f"/stories/chapters/{chapter['id']}",
        json={"content": "Second draft.", "expected_revision": chapter["revision"]},
    )
    assert first.status_code == 200
    assert first.json()["revision"] == chapter["revision"] + 1

    stale = await user_client.put(
        f"/stories/chapters/{chapter['id']}",
        json={"content": "Third draft.", "expected_revision": chapter["revision"]},
    )
    assert stale.status_code == 409

    current = await user_client.get(f"/stories/chapters/{chapter['id']}")
    assert current.json()["content"] == "Second draft."


async def test_correct_revision_succeeds_and_increments(user_client):
    _story, chapter = await _story_and_chapter(user_client)
    revision = chapter["revision"]

    for index in range(3):
        response = await user_client.put(
            f"/stories/chapters/{chapter['id']}",
            json={"content": f"Draft {index}.", "expected_revision": revision},
        )
        assert response.status_code == 200
        revision = response.json()["revision"]

    assert revision == chapter["revision"] + 3


async def test_unchanged_save_does_not_increment_revision(user_client):
    _story, chapter = await _story_and_chapter(user_client)
    response = await user_client.put(
        f"/stories/chapters/{chapter['id']}",
        json={"content": "First draft.", "expected_revision": chapter["revision"]},
    )
    assert response.status_code == 200
    assert response.json()["revision"] == chapter["revision"]


async def test_word_count_tracks_content(user_client):
    _story, chapter = await _story_and_chapter(user_client)
    response = await user_client.put(
        f"/stories/chapters/{chapter['id']}",
        json={"content": "one two three four five", "expected_revision": chapter["revision"]},
    )
    assert response.status_code == 200
    assert response.json()["word_count"] == 5
