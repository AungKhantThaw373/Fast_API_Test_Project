"""Wiki API: entities, aliases, facts, relationships, threads, events, inbox."""

from uuid import UUID

import pytest

from app.models.wiki_models import EntityMention
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
    # A writer may add a field value by hand without a manuscript source.
    manual = await user_client.post(
        f"/entities/{entity['id']}/facts", json={"predicate": "eye_color", "value_text": "grey"}
    )
    assert manual.status_code == 201, manual.text
    assert manual.json()["chapter_id"] is None
    assert manual.json()["created_by"] == "human"

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

    story_id = await _story(user_client)
    story_uuid = UUID(story_id)
    with pytest.raises(Exception) as error:
        await entity_service.create_entity(
            session, story_id=story_uuid, entity_type="character", name=" "
        )
    assert getattr(error.value, "status_code", None) == 422

    entity = await entity_service.create_entity(
        session, story_id=story_uuid, entity_type="character", name="Mira Voss"
    )
    await session.commit()

    chapter = await _chapter(user_client, story_id, content="Her eyes were grey.")
    with pytest.raises(Exception) as provenance:
        await fact_service.create_fact(
            session,
            entity,
            FactCreate(predicate="eye_color", value_text="grey"),
            created_by="ai",
        )
    assert getattr(provenance.value, "status_code", None) == 422
    with pytest.raises(Exception) as unverified:
        await fact_service.create_fact(
            session,
            entity,
            FactCreate(
                predicate="eye_color",
                value_text="grey",
                chapter_id=UUID(chapter["id"]),
                quote="Her eyes were green.",
            ),
            created_by="ai",
        )
    assert getattr(unverified.value, "status_code", None) == 422
    assert "does not appear" in str(getattr(unverified.value, "detail", ""))


async def test_merge_endpoint_moves_facts_and_honours_dry_run(user_client):
    story_id = await _story(user_client)
    keep = await _entity(user_client, story_id, name="Mira Voss")
    gone = await _entity(user_client, story_id, name="Captain Voss")
    chapter = await _chapter(user_client, story_id, content="The captain gave the order.")
    fact = await user_client.post(
        f"/entities/{gone['id']}/facts",
        json={"predicate": "rank", "value_text": "captain", "chapter_id": chapter["id"]},
    )
    assert fact.status_code == 201, fact.text

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


async def test_custom_entity_types_and_relationship_edits(user_client):
    story_id = await _story(user_client)
    technique = await _entity(
        user_client, story_id, name="Limitless", entity_type="Cursed Technique"
    )
    assert technique["entity_type"] == "cursed_technique"
    invalid = await user_client.post(
        f"/stories/{story_id}/entities",
        json={"name": "Nine Lives", "entity_type": "9lives"},
    )
    assert invalid.status_code == 422

    hero = await _entity(user_client, story_id, name="Satoru")
    rival = await _entity(user_client, story_id, name="Suguru")
    first = await user_client.post(
        f"/entities/{hero['id']}/relationships",
        json={"to_entity_id": rival["id"], "relationship_type": "friend_of"},
    )
    assert first.status_code == 201, first.text
    rival_link = await user_client.post(
        f"/entities/{hero['id']}/relationships",
        json={"to_entity_id": rival["id"], "relationship_type": "rival_of"},
    )
    assert rival_link.status_code == 201, rival_link.text

    patched = await user_client.patch(
        f"/relationships/{first.json()['id']}",
        json={"relationship_type": "best_friend_of", "description": "Since school."},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["relationship_type"] == "best_friend_of"
    assert patched.json()["description"] == "Since school."

    conflict = await user_client.patch(
        f"/relationships/{first.json()['id']}",
        json={"relationship_type": "rival_of"},
    )
    assert conflict.status_code == 409


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




async def test_thread_board_metadata_and_last_mention(user_client, session):
    story_id = await _story(user_client)
    first = await _chapter(user_client, story_id, 1)
    second = await _chapter(user_client, story_id, 2)
    entity = await _entity(user_client, story_id)
    thread = await user_client.post(
        f"/stories/{story_id}/threads",
        json={
            "title": "Who betrayed the Watch?",
            "setup_chapter_id": first["id"],
            "linked_entity_ids": [entity["id"]],
        },
    )
    assert thread.status_code == 201, thread.text
    session.add_all(
        [
            EntityMention(
                entity_id=UUID(entity["id"]),
                chapter_id=UUID(first["id"]),
                line_start=1,
                line_end=1,
                quote="Mira Voss crossed the yard.",
            ),
            EntityMention(
                entity_id=UUID(entity["id"]),
                chapter_id=UUID(second["id"]),
                line_start=2,
                line_end=2,
                quote="The captain watched Mira.",
            ),
        ]
    )
    await session.commit()

    listed = await user_client.get(f"/stories/{story_id}/threads")
    assert listed.status_code == 200
    row = listed.json()["threads"][0]
    assert row["linked_entities"] == [
        {"id": entity["id"], "name": "Mira Voss", "entity_type": "character"}
    ]
    assert row["setup_chapter_number"] == 1
    assert row["setup_chapter_title"] == "Chapter 1"
    assert row["last_mention"]["chapter_number"] == 2
    assert row["last_mention"]["line"] == 2
    assert row["last_mention"]["quote"] == "The captain watched Mira."

    moved = await user_client.patch(
        f"/threads/{thread.json()['id']}",
        json={"state": "resolved", "payoff_chapter_id": second["id"]},
    )
    assert moved.status_code == 200
    assert moved.json()["payoff_chapter_number"] == 2


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
    other = await _entity(alice, story_id, name="Jax")
    relationship = await alice.post(
        f"/entities/{entity['id']}/relationships",
        json={"to_entity_id": other["id"], "relationship_type": "knows"},
    )
    assert relationship.status_code == 201

    assert (await bob.get(f"/entities/{entity['id']}")).status_code == 404
    assert (
        await bob.patch(
            f"/relationships/{relationship.json()['id']}",
            json={"description": "stolen"},
        )
    ).status_code == 404
    assert (await bob.get(f"/stories/{story_id}/entities")).status_code == 404
    assert (await bob.get(f"/stories/{story_id}/inbox")).status_code == 404
    assert (
        await bob.post(
            f"/entities/{entity['id']}/facts",
            json={"predicate": "eye_color", "value_text": "grey", "chapter_id": str(UUID(int=0))},
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


async def test_merge_can_be_undone_from_its_audit(user_client):
    story_id = await _story(user_client)
    keep = await _entity(user_client, story_id, name="Mira Voss")
    gone = await _entity(
        user_client, story_id, name="Captain Voss", aliases=[{"alias": "the captain"}]
    )
    chapter = await _chapter(user_client, story_id, content="Captain Voss gave the order.\n")
    fact = await user_client.post(
        f"/entities/{gone['id']}/facts",
        json={
            "predicate": "rank",
            "value_text": "captain",
            "chapter_id": chapter["id"],
            "quote": "Captain Voss gave the order.",
        },
    )
    assert fact.status_code == 201
    relationship = await user_client.post(
        f"/entities/{gone['id']}/relationships",
        json={"to_entity_id": keep["id"], "relationship_type": "alias_of"},
    )
    assert relationship.status_code == 201

    merged = await user_client.post(
        f"/entities/{gone['id']}/merge", json={"target_id": keep["id"]}
    )
    assert merged.status_code == 200
    assert (await user_client.get(f"/entities/{gone['id']}")).status_code == 409

    undone = await user_client.post(f"/entities/{gone['id']}/unmerge")
    assert undone.status_code == 200, undone.text
    assert undone.json()["target_id"] == keep["id"]
    assert undone.json()["reverted_at"] is not None

    restored = await user_client.get(f"/entities/{gone['id']}")
    assert restored.status_code == 200
    assert restored.json()["merged_into_id"] is None
    assert restored.json()["status"] == "active"
    # The fact and the relationship came back with it.
    facts = (await user_client.get(f"/entities/{gone['id']}/facts")).json()["facts"]
    assert [row["id"] for row in facts] == [fact.json()["id"]]
    rels = (await user_client.get(f"/entities/{gone['id']}/relationships")).json()
    assert [row["id"] for row in rels["outgoing"]] == [relationship.json()["id"]]
    target_facts = (await user_client.get(f"/entities/{keep['id']}/facts")).json()["facts"]
    assert target_facts == []

    # Only one merge exists, and it has been reverted.
    twice = await user_client.post(f"/entities/{gone['id']}/unmerge")
    assert twice.status_code == 404


async def test_canon_exceptions_suppress_matching_findings(user_client):
    from app.services.canon_exceptions import filter_exceptions
    from app.services.finding_filter import DraftFinding

    story_id = await _story(user_client)
    created = await user_client.post(
        f"/stories/{story_id}/exceptions",
        json={
            "scope": "pattern",
            "pattern": "eye colour",
            "reason": "Her eyes change colour after the trial in chapter 7.",
        },
    )
    assert created.status_code == 201, created.text

    finding = DraftFinding(
        draft_quote="Her eyes were bright green now.",
        draft_line=3,
        earlier_quote="Her eyes were grey in the morning light.",
        earlier_chapter_id=UUID(int=1),
        earlier_chapter_number=1,
        explanation="Eye colour contradicts chapter 1.",
        confidence=80,
    )
    other = DraftFinding(
        draft_quote="The gate stood open.",
        draft_line=9,
        earlier_quote="The gate was barred and locked at dusk.",
        earlier_chapter_id=UUID(int=1),
        earlier_chapter_number=2,
        explanation="The gate state contradicts chapter 2.",
        confidence=70,
    )
    from app.db import async_session

    async with async_session() as session:
        kept, suppressed = await filter_exceptions(
            session, UUID(story_id), [finding, other]
        )
    assert suppressed == 1
    assert [item.draft_line for item in kept] == [9]

    listed = await user_client.get(f"/stories/{story_id}/exceptions")
    assert len(listed.json()["exceptions"]) == 1

    bad_scope = await user_client.post(
        f"/stories/{story_id}/exceptions", json={"scope": "pattern", "reason": "no pattern"}
    )
    assert bad_scope.status_code == 422

    removed = await user_client.delete(f"/exceptions/{created.json()['id']}")
    assert removed.status_code == 204
    assert (await user_client.get(f"/stories/{story_id}/exceptions")).json()["exceptions"] == []


async def test_old_bible_endpoints_edit_entities(user_client):
    """The pre-Phase-4 studio UI edits ids that now belong to entities/threads."""
    story_id = await _story(user_client)
    entity = await _entity(user_client, story_id, name="Mira Voss")
    chapter = await _chapter(user_client, story_id, content="Mira Voss has grey eyes.")
    proposal = await user_client.post(
        f"/entities/{entity['id']}/facts",
        json={
            "predicate": "summary",
            "value_text": "A captain.",
            "chapter_id": chapter["id"],
            "quote": "Mira Voss has grey eyes.",
            "status": "proposed",
        },
    )
    assert proposal.status_code == 201

    decision = await user_client.patch(
        f"/stories/bible/{entity['id']}/decision", json={"status": "accepted"}
    )
    assert decision.status_code == 200, decision.text
    assert decision.json()["status"] == "accepted"
    # A second decision is refused, exactly like the legacy flow.
    again = await user_client.patch(
        f"/stories/bible/{entity['id']}/decision", json={"status": "accepted"}
    )
    assert again.status_code == 409

    edited = await user_client.put(
        f"/stories/bible/{entity['id']}",
        json={
            "category": "character",
            "name": "Mira Voss",
            "description": "A captain with grey eyes.",
            "details": {},
        },
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["description"] == "A captain with grey eyes."
    entity_now = await user_client.get(f"/entities/{entity['id']}")
    assert entity_now.json()["summary"] == "A captain with grey eyes."

    thread = await user_client.post(
        f"/stories/{story_id}/threads", json={"title": "Who opened the gate?"}
    )
    resolved = await user_client.patch(
        f"/stories/bible/{thread.json()['id']}/thread", json={"thread_state": "resolved"}
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["thread_state"] == "resolved"
    assert resolved.json()["category"] == "plot_thread"

    deleted = await user_client.delete(f"/stories/bible/{entity['id']}")
    assert deleted.status_code == 204
    archived = await user_client.get(f"/entities/{entity['id']}")
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    listed = await user_client.get(f"/stories/{story_id}/entities")
    assert listed.json()["entities"] == []
