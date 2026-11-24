"""Wiki API: entities, aliases, facts, relationships, threads, events, inbox."""

from uuid import UUID

import pytest

from app.services import entities as entity_service


async def _story(client, title="Wiki Story") -> str:
    response = await client.post("/stories", json={"title": title})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _chapter(client, story_id: str, number: int = 1, content: str | None = None) -> dict:
    body = {
        "chapter_number": number,
        "title": f"Chapter {number}",
        "content": content or f"Mira Voss crossed the yard on day {number}.\nThe captain watched.\n",
    }
    response = await client.post(f"/stories/{story_id}/chapters", json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def _entity(client, story_id: str, name="Mira Voss", entity_type="character", **extra):
    response = await client.post(
        f"/stories/{story_id}/entities",
        json={"name": name, "entity_type": entity_type, **extra},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_entity_create_list_and_alias(user_client):
    story_id = await _story(user_client)
    created = await _entity(
        user_client, story_id, aliases=[{"alias": "the captain", "alias_type": "title"}]
    )
    assert created["name"] == "Mira Voss"
    assert {alias["alias"] for alias in created["aliases"]} >= {"Mira Voss", "the captain"}

    listed = await user_client.get(f"/stories/{story_id}/entities")
    assert listed.status_code == 200
    assert [entity["id"] for entity in listed.json()["entities"]] == [created["id"]]

    added = await user_client.post(
        f"/entities/{created['id']}/aliases", json={"alias": "Lady Voss", "alias_type": "title"}
    )
    assert added.status_code == 201
    duplicate = await user_client.post(
        f"/entities/{created['id']}/aliases", json={"alias": "mira voss"}
    )
    assert duplicate.status_code == 409


async def test_duplicate_entity_name_is_rejected(user_client):
    story_id = await _story(user_client)
    await _entity(user_client, story_id, name="Mira Voss")
    conflict = await user_client.post(
        f"/stories/{story_id}/entities",
        json={"name": "mira voss", "entity_type": "location"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["entity_id"]


async def test_entity_search_and_appearances(user_client):
    story_id = await _story(user_client)
    entity = await _entity(user_client, story_id)
    chapter = await _chapter(user_client, story_id, content="Mira Voss crossed the yard.\n")
    await user_client.post(
        f"/stories/{story_id}/entities",
        json={"name": "Mirage", "entity_type": "location"},
    )

    found = await user_client.get(
        "/entities/search", params={"story_id": story_id, "q": "mira"}
    )
    assert found.status_code == 200
    names = {item["name"] for item in found.json()["entities"]}
    assert "Mira Voss" in names

    # Appearances come from mention extraction, which the indexer normally runs.
    from app.db import async_session

    async with async_session() as session:
        await entity_service.extract_mentions(
            session, entity["story_id"], chapter["id"], chapter["content"]
        )
        await session.commit()

    appearances = await user_client.get(f"/entities/{entity['id']}/appearances")
    assert appearances.status_code == 200
    rows = appearances.json()["appearances"]
    assert len(rows) == 1
    assert rows[0]["chapter_number"] == 1
    assert rows[0]["line_start"] == 1
    assert "Mira Voss" in rows[0]["quote"]


async def test_fact_accept_supersedes_previous_value(user_client, session):
    story_id = await _story(user_client)
    entity = await _entity(user_client, story_id)
    chapter = await _chapter(user_client, story_id, content="Her eyes were grey.\n")

    first = await user_client.post(
        f"/entities/{entity['id']}/facts",
        json={
            "predicate": "eye_color",
            "value_text": "grey",
            "chapter_id": chapter["id"],
            "quote": "Her eyes were grey.",
        },
    )
    assert first.status_code == 201, first.text
    assert first.json()["status"] == "accepted"
    assert first.json()["line_start"] == 1

    second = await user_client.post(
        f"/entities/{entity['id']}/facts",
        json={
            "predicate": "eye_color",
            "value_text": "green",
            "chapter_id": chapter["id"],
            "quote": "Her eyes were grey.",
            "status": "proposed",
        },
    )
    assert second.status_code == 201
    assert second.json()["status"] == "proposed"

    accepted = await user_client.post(f"/facts/{second.json()['id']}/accept")
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"
    assert accepted.json()["supersedes_id"] == first.json()["id"]

    facts = (
        await user_client.get(f"/entities/{entity['id']}/facts", params={"predicate": "eye_color"})
    ).json()["facts"]
    statuses = {fact["id"]: fact["status"] for fact in facts}
    assert statuses[first.json()["id"]] == "superseded"
    assert statuses[second.json()["id"]] == "accepted"

    rejected = await user_client.post(f"/facts/{second.json()['id']}/reject")
    assert rejected.json()["status"] == "rejected"


async def test_fact_requires_a_value_and_owned_chapter(user_client):
    story_id = await _story(user_client)
    entity = await _entity(user_client, story_id)
    empty = await user_client.post(
        f"/entities/{entity['id']}/facts", json={"predicate": "eye_color"}
    )
    assert empty.status_code == 422

    foreign = await _story(user_client, "Other")
    other_chapter = await _chapter(user_client, foreign)
    mismatched = await user_client.post(
        f"/entities/{entity['id']}/facts",
        json={"predicate": "eye_color", "value_text": "grey", "chapter_id": other_chapter["id"]},
    )
    assert mismatched.status_code == 404


async def test_ai_fact_requires_provenance(user_client, session):
    from app.schemas.wiki import FactCreate
    from app.services import facts as fact_service

    story_uuid = UUID(await _story(user_client))
    with pytest.raises(Exception) as error:
        await entity_service.create_entity(
            session, story_id=story_uuid, entity_type="character", name=" "
        )
    assert getattr(error.value, "status_code", None) == 422

    entity = await entity_service.create_entity(
        session, story_id=story_uuid, entity_type="character", name="Mira Voss"
    )
    await session.commit()

    with pytest.raises(Exception) as provenance:
        await fact_service.create_fact(
            session,
            entity,
            FactCreate(predicate="eye_color", value_text="grey"),
            created_by="ai",
        )
    assert getattr(provenance.value, "status_code", None) == 422


async def test_merge_endpoint_moves_facts_and_honours_dry_run(user_client):
    story_id = await _story(user_client)
    keep = await _entity(user_client, story_id, name="Mira Voss")
    gone = await _entity(user_client, story_id, name="Captain Voss")
    fact = await user_client.post(
        f"/entities/{gone['id']}/facts",
        json={"predicate": "rank", "value_text": "captain"},
    )
    assert fact.status_code == 201

    preview = await user_client.post(
        f"/entities/{gone['id']}/merge", json={"target_id": keep["id"], "dry_run": True}
    )
    assert preview.status_code == 200
    assert preview.json()["moved"]["facts"] == 1
    still_there = await user_client.get(f"/entities/{gone['id']}/facts")
    assert len(still_there.json()["facts"]) == 1

    merged = await user_client.post(
        f"/entities/{gone['id']}/merge", json={"target_id": keep["id"]}
    )
    assert merged.status_code == 200
    assert merged.json()["moved"]["facts"] == 1

    # The merged-away id stops accepting edits but its facts moved with the merge.
    stale = await user_client.get(f"/entities/{gone['id']}")
    assert stale.status_code == 409
    facts = (await user_client.get(f"/entities/{keep['id']}/facts")).json()["facts"]
    assert [row["predicate"] for row in facts] == ["rank"]

    self_merge = await user_client.post(
        f"/entities/{keep['id']}/merge", json={"target_id": keep["id"]}
    )
    assert self_merge.status_code == 422


async def test_relationships_and_guards(user_client):
    story_id = await _story(user_client)
    hero = await _entity(user_client, story_id, name="Mira Voss")
    rival = await _entity(user_client, story_id, name="Jax")
    created = await user_client.post(
        f"/entities/{hero['id']}/relationships",
        json={"to_entity_id": rival["id"], "relationship_type": "rival_of"},
    )
    assert created.status_code == 201, created.text
    duplicate = await user_client.post(
        f"/entities/{hero['id']}/relationships",
        json={"to_entity_id": rival["id"], "relationship_type": "rival_of"},
    )
    assert duplicate.status_code == 409
    self_link = await user_client.post(
        f"/entities/{hero['id']}/relationships",
        json={"to_entity_id": hero["id"], "relationship_type": "self"},
    )
    assert self_link.status_code == 422

    listed = await user_client.get(f"/entities/{hero['id']}/relationships")
    assert [row["relationship_type"] for row in listed.json()["outgoing"]] == ["rival_of"]
    assert listed.json()["incoming"] == []

    deleted = await user_client.delete(f"/relationships/{created.json()['id']}")
    assert deleted.status_code == 204


async def test_threads_and_events(user_client):
    story_id = await _story(user_client)
    chapter = await _chapter(user_client, story_id)
    thread = await user_client.post(
        f"/stories/{story_id}/threads",
        json={"title": "Who betrayed the Watch?", "setup_chapter_id": chapter["id"]},
    )
    assert thread.status_code == 201, thread.text
    assert thread.json()["state"] == "open"

    unresolved = await user_client.patch(
        f"/threads/{thread.json()['id']}", json={"state": "resolved"}
    )
    assert unresolved.status_code == 422

    resolved = await user_client.patch(
        f"/threads/{thread.json()['id']}",
        json={"state": "resolved", "payoff_chapter_id": chapter["id"]},
    )
    assert resolved.status_code == 200
    assert resolved.json()["state"] == "resolved"

    listed = await user_client.get(f"/stories/{story_id}/threads")
    assert len(listed.json()["threads"]) == 1

    event = await user_client.post(
        f"/stories/{story_id}/events",
        json={"chapter_id": chapter["id"], "summary": "Mira crosses the yard.", "quote": "yard"},
    )
    assert event.status_code == 201, event.text
    assert event.json()["timeline_order"] == 1000.0

    updated = await user_client.put(
        f"/events/{event.json()['id']}", json={"summary": "Mira crosses the yard slowly."}
    )
    assert updated.status_code == 200
    events = await user_client.get(f"/stories/{story_id}/events")
    assert len(events.json()["events"]) == 1

    assert (await user_client.delete(f"/events/{event.json()['id']}")).status_code == 204
    assert (await user_client.delete(f"/threads/{thread.json()['id']}")).status_code == 204


async def test_inbox_lists_proposals_before_findings(user_client):
    story_id = await _story(user_client)
    entity = await _entity(user_client, story_id)
    chapter = await _chapter(user_client, story_id, content="Her eyes were grey.\n")
    for value, status in (("grey", "accepted"), ("green", "proposed")):
        await user_client.post(
            f"/entities/{entity['id']}/facts",
            json={
                "predicate": "eye_color",
                "value_text": value,
                "chapter_id": chapter["id"],
                "quote": "Her eyes were grey.",
                "status": status,
            },
        )

    inbox = await user_client.get(f"/stories/{story_id}/inbox")
    assert inbox.status_code == 200
    items = inbox.json()["items"]
    assert [item["kind"] for item in items] == ["fact"]
    assert items[0]["summary"] == "green"
    assert items[0]["why_held"] == "Already recorded as 'grey'."
    assert items[0]["source"]["chapter_number"] == 1
    assert items[0]["actions"] == ["accept", "reject", "edit"]

    only_findings = await user_client.get(
        f"/stories/{story_id}/inbox", params={"kind": "finding"}
    )
    assert only_findings.json()["items"] == []


async def test_bible_compatibility_shape(user_client):
    story_id = await _story(user_client)
    entity = await _entity(user_client, story_id, name="Mira Voss", summary="A captain.")
    chapter = await _chapter(user_client, story_id, content="Mira Voss has grey eyes.\n")
    await user_client.post(
        f"/entities/{entity['id']}/facts",
        json={
            "predicate": "summary",
            "value_text": "A captain of the Watch.",
            "chapter_id": chapter["id"],
            "quote": "Mira Voss has grey eyes.",
            "status": "proposed",
        },
    )
    thread = await user_client.post(
        f"/stories/{story_id}/threads", json={"title": "Who betrayed the Watch?"}
    )
    assert thread.status_code == 201

    response = await user_client.get(f"/stories/{story_id}/bible")
    assert response.status_code == 200
    entries = response.json()["entries"]
    assert {entry["category"] for entry in entries} == {"character", "plot_thread"}
    character = next(entry for entry in entries if entry["category"] == "character")
    # The old client's keys are all present, with old-style values.
    assert set(character) == {
        "id",
        "category",
        "name",
        "description",
        "status",
        "thread_state",
        "confidence",
        "source_chapter_id",
        "source_quote",
        "details",
        "updated_at",
    }
    assert character["status"] == "suggested"
    assert character["description"] == "A captain of the Watch."
    assert character["source_quote"] == "Mira Voss has grey eyes."
    plot_thread = next(entry for entry in entries if entry["category"] == "plot_thread")
    assert plot_thread["thread_state"] == "open"
    assert plot_thread["id"] == thread.json()["id"]


async def test_other_users_cannot_touch_entities(make_client):
    alice = await make_client("alice", "alice@example.com")
    bob = await make_client("bob", "bob@example.com")
    story_id = await _story(alice)
    entity = await _entity(alice, story_id)

    assert (await bob.get(f"/entities/{entity['id']}")).status_code == 404
    assert (await bob.get(f"/stories/{story_id}/entities")).status_code == 404
    assert (await bob.get(f"/stories/{story_id}/inbox")).status_code == 404
    assert (
        await bob.post(
            f"/entities/{entity['id']}/facts",
            json={"predicate": "eye_color", "value_text": "grey"},
        )
    ).status_code == 404
    assert (
        await bob.post(
            f"/stories/{story_id}/threads", json={"title": "Stolen thread"}
        )
    ).status_code == 404
    assert (
        await bob.post(f"/entities/{entity['id']}/merge", json={"target_id": entity["id"]})
    ).status_code == 404
    own_facts = await alice.get(f"/entities/{entity['id']}/facts")
    assert own_facts.status_code == 200
