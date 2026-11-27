"""Arcs group chapters and filter the wiki."""



async def _story(client) -> str:
    response = await client.post("/stories", json={"title": "Arcs"})
    assert response.status_code == 201
    return response.json()["id"]


async def test_arcs_default_group_and_reassignment(user_client):
    story_id = await _story(user_client)
    chapters = []
    for index in range(3):
        response = await user_client.post(
            f"/stories/{story_id}/chapters", json={"title": f"Chapter {index + 1}"}
        )
        chapters.append(response.json()["id"])

    initial = (await user_client.get(f"/stories/{story_id}/arcs")).json()
    # A new story has no arcs yet; the rail falls back to a flat list.
    assert initial == []

    created = await user_client.post(f"/stories/{story_id}/arcs", json={"name": "The long winter"})
    assert created.status_code == 201, created.text
    arc = created.json()

    moved = await user_client.put(
        f"/stories/{story_id}/arcs",
        json={"arc_id": arc["id"], "chapter_ids": chapters[:2]},
    )
    assert moved.json() == {"updated": 2}

    listed = (await user_client.get(f"/stories/{story_id}/arcs")).json()
    assert listed[0]["chapter_count"] == 2
    assert listed[0]["first_chapter_number"] == 1
    assert listed[0]["last_chapter_number"] == 2

    detail = (await user_client.get(f"/stories/chapters/{chapters[0]}")).json()
    assert detail["arc_id"] == arc["id"]

    # The story payload drives the rail; it must carry the arc without a reload.
    story_payload = (await user_client.get(f"/stories/{story_id}")).json()
    assert story_payload["chapters"][0]["arc_id"] == arc["id"]

    # Unassigning puts the chapter back in the ungrouped bucket.
    await user_client.put(
        f"/stories/{story_id}/arcs", json={"arc_id": None, "chapter_ids": chapters[:2]}
    )
    assert (await user_client.get(f"/stories/{story_id}/arcs")).json()[0]["chapter_count"] == 0

    renamed = await user_client.patch(f"/arcs/{arc['id']}", json={"name": "Act one"})
    assert renamed.json()["name"] == "Act one"

    deleted = await user_client.delete(f"/arcs/{arc['id']}")
    assert deleted.status_code == 204
    assert (await user_client.get(f"/stories/{story_id}/arcs")).json() == []


async def test_arc_assignment_rejects_a_foreign_arc(user_client):
    mine = await _story(user_client)
    other = await _story(user_client)
    chapter = (await user_client.post(f"/stories/{mine}/chapters", json={"title": "One"})).json()
    foreign = (await user_client.post(f"/stories/{other}/arcs", json={"name": "Theirs"})).json()

    denied = await user_client.put(
        f"/stories/{mine}/arcs",
        json={"arc_id": foreign["id"], "chapter_ids": [chapter["id"]]},
    )
    assert denied.status_code == 404


async def test_wiki_can_filter_entities_by_arc(user_client, session):
    story_id = await _story(user_client)
    chapters = []
    for index in range(2):
        response = await user_client.post(
            f"/stories/{story_id}/chapters",
            json={"title": f"Chapter {index + 1}", "content": "Mira Voss crossed the yard."},
        )
        chapters.append(response.json()["id"])

    early = (await user_client.post(f"/stories/{story_id}/arcs", json={"name": "Early"})).json()
    await user_client.put(f"/stories/{story_id}/arcs", json={"arc_id": early["id"], "chapter_ids": [chapters[0]]})

    entity = await user_client.post(
        f"/stories/{story_id}/entities", json={"name": "Mira Voss", "entity_type": "character"}
    )
    entity_id = entity.json()["id"]

    # A fact recorded in an arc chapter puts the entity in that arc, even before
    # mention extraction has run.
    created = await user_client.post(
        f"/entities/{entity_id}/facts",
        json={
            "predicate": "role",
            "value_text": "gatekeeper",
            "chapter_id": chapters[0],
            "quote": "Mira Voss crossed the yard.",
        },
    )
    assert created.status_code == 201, created.text

    inside = (await user_client.get(f"/stories/{story_id}/entities?arc_id={early['id']}")).json()
    assert [row["id"] for row in inside["entities"]] == [entity_id]

    late = (await user_client.post(f"/stories/{story_id}/arcs", json={"name": "Late"})).json()
    outside = (await user_client.get(f"/stories/{story_id}/entities?arc_id={late['id']}")).json()
    assert outside["entities"] == []
