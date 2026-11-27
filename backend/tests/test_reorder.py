import uuid

import pytest


@pytest.fixture
async def story_with_chapters(user_client):
    story = (await user_client.post("/stories", json={"title": "Order story"})).json()
    chapters = []
    for index in range(3):
        response = await user_client.post(
            f"/stories/{story['id']}/chapters",
            json={"title": f"Chapter {index + 1}", "content": f"Body {index + 1}"},
        )
        assert response.status_code == 201
        chapters.append(response.json())
    return story, chapters


async def test_reorder_three_chapters(user_client, story_with_chapters):
    story, chapters = story_with_chapters
    reversed_ids = [chapter["id"] for chapter in reversed(chapters)]

    response = await user_client.put(
        f"/stories/{story['id']}/chapters/order", json={"chapter_ids": reversed_ids}
    )
    assert response.status_code == 200
    ordered = response.json()["chapters"]
    assert [chapter["id"] for chapter in ordered] == reversed_ids
    assert [chapter["chapter_number"] for chapter in ordered] == [1, 2, 3]

    story_after = (await user_client.get(f"/stories/{story['id']}")).json()
    assert [chapter["id"] for chapter in story_after["chapters"]] == reversed_ids


async def test_reorder_missing_a_chapter_is_rejected(user_client, story_with_chapters):
    story, chapters = story_with_chapters
    response = await user_client.put(
        f"/stories/{story['id']}/chapters/order",
        json={"chapter_ids": [chapters[0]["id"], chapters[1]["id"]]},
    )
    assert response.status_code == 422


async def test_reorder_with_a_duplicate_is_rejected(user_client, story_with_chapters):
    story, chapters = story_with_chapters
    response = await user_client.put(
        f"/stories/{story['id']}/chapters/order",
        json={
            "chapter_ids": [chapters[0]["id"], chapters[0]["id"], chapters[2]["id"]],
        },
    )
    assert response.status_code == 422


async def test_reorder_with_an_unknown_chapter_is_rejected(user_client, story_with_chapters):
    story, chapters = story_with_chapters
    response = await user_client.put(
        f"/stories/{story['id']}/chapters/order",
        json={
            "chapter_ids": [chapters[0]["id"], chapters[1]["id"], str(uuid.uuid4())],
        },
    )
    assert response.status_code == 422


async def test_reorder_cannot_touch_another_users_chapters(make_client, story_with_chapters):
    story, chapters = story_with_chapters
    stranger = await make_client("stranger", "stranger@example.com")
    response = await stranger.put(
        f"/stories/{story['id']}/chapters/order",
        json={"chapter_ids": [chapter["id"] for chapter in chapters]},
    )
    assert response.status_code == 404
