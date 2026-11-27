import pytest


async def _create_story(client, title="A story") -> dict:
    response = await client.post("/stories", json={"title": title})
    assert response.status_code == 201
    return response.json()


async def _create_chapter(client, story_id: str, title="Chapter one") -> dict:
    response = await client.post(
        f"/stories/{story_id}/chapters", json={"title": title, "content": "Some prose here."}
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
async def two_users(make_client):
    alice = await make_client("alice", "alice@example.com")
    bob = await make_client("bob", "bob@example.com")
    return alice, bob


async def test_cannot_read_or_list_another_users_story(two_users):
    alice, bob = two_users
    story = await _create_story(alice)

    assert (await bob.get(f"/stories/{story['id']}")).status_code == 404
    listing = await bob.get("/stories")
    assert listing.status_code == 200
    assert listing.json()["stories"] == []


async def test_cannot_update_or_delete_another_users_story(two_users):
    alice, bob = two_users
    story = await _create_story(alice)

    assert (await bob.patch(f"/stories/{story['id']}", json={"title": "Stolen"})).status_code == 404
    assert (await bob.delete(f"/stories/{story['id']}")).status_code == 404
    assert (await alice.get(f"/stories/{story['id']}")).status_code == 200


async def test_cannot_read_or_write_another_users_chapter(two_users):
    alice, bob = two_users
    story = await _create_story(alice)
    chapter = await _create_chapter(alice, story["id"])

    assert (await bob.get(f"/stories/chapters/{chapter['id']}")).status_code == 404
    update = await bob.put(
        f"/stories/chapters/{chapter['id']}",
        json={"title": "Hijacked", "content": "nope", "expected_revision": chapter["revision"]},
    )
    assert update.status_code == 404
    assert (await bob.delete(f"/stories/chapters/{chapter['id']}")).status_code == 404
    assert (await alice.get(f"/stories/chapters/{chapter['id']}")).status_code == 200


async def test_cannot_read_or_mutate_another_users_bible_entry(two_users):
    alice, bob = two_users
    story = await _create_story(alice)
    created = await alice.post(
        f"/stories/{story['id']}/bible",
        json={
            "category": "character",
            "name": "Mira Voss",
            "description": "A captain.",
            "details": {},
        },
    )
    assert created.status_code == 201
    entry = created.json()

    assert (await bob.get(f"/stories/{story['id']}/bible")).status_code == 404
    assert (await bob.delete(f"/stories/bible/{entry['id']}")).status_code == 404
    assert (
        await bob.patch(f"/stories/bible/{entry['id']}/decision", json={"status": "dismissed"})
    ).status_code == 404
    assert (
        await bob.put(
            f"/stories/bible/{entry['id']}",
            json={
                "category": "character",
                "name": "Mira Voss",
                "description": "Changed.",
                "details": {},
            },
        )
    ).status_code == 404
