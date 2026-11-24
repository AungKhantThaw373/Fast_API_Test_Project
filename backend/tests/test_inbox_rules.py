"""Inbox decisions, merge proposals, and auto-accept rules."""

from uuid import UUID


async def _story(client) -> str:
	response = await client.post("/stories", json={"title": "Inbox"})
	assert response.status_code == 201
	return response.json()["id"]


async def _chapter(client, story_id: str, content: str) -> dict:
	response = await client.post(
		f"/stories/{story_id}/chapters",
		json={"title": "One", "content": content},
	)
	assert response.status_code == 201
	return response.json()


async def _entity(client, story_id: str, name: str) -> dict:
	response = await client.post(
		f"/stories/{story_id}/entities", json={"name": name, "entity_type": "character"}
	)
	assert response.status_code == 201, response.text
	return response.json()


async def _fact(
    client,
    entity_id: str,
    chapter_id: str,
    value: str,
    *,
    status="proposed",
    confidence=90,
    quote="Her eyes were grey.",
):
	response = await client.post(
		f"/entities/{entity_id}/facts",
		json={
			"predicate": "eye_color",
			"value_text": value,
			"chapter_id": chapter_id,
			"quote": quote,
			"status": status,
			"confidence": confidence,
		},
	)
	assert response.status_code == 201, response.text
	return response.json()


async def test_batch_decision_accepts_and_rejects(user_client):
	story_id = await _story(user_client)
	chapter = await _chapter(user_client, story_id, "Her eyes were grey.")
	entity = await _entity(user_client, story_id, "Mira Voss")
	first = await _fact(user_client, entity["id"], chapter["id"], "grey")
	second = await _fact(user_client, entity["id"], chapter["id"], "green")

	accepted = await user_client.post(
		f"/stories/{story_id}/inbox/decide",
		json={"ids": [first["id"]], "action": "accept"},
	)
	assert accepted.status_code == 200, accepted.text
	assert accepted.json() == {"facts": 1, "findings": 0, "merges": 0, "skipped": 0, "action": "accept"}

	rejected = await user_client.post(
		f"/stories/{story_id}/inbox/decide",
		json={"ids": [second["id"]], "action": "reject"},
	)
	assert rejected.json()["facts"] == 1

	inbox = await user_client.get(f"/stories/{story_id}/inbox")
	assert inbox.json()["items"] == []


async def test_merge_proposals_appear_in_inbox_and_can_be_dismissed(user_client):
	story_id = await _story(user_client)
	await _entity(user_client, story_id, "Zephyrion")
	await _entity(user_client, story_id, "Zephyrionn")

	proposals = await user_client.get(f"/stories/{story_id}/merge-proposals")
	assert proposals.status_code == 200, proposals.text
	rows = proposals.json()
	assert len(rows) == 1
	assert rows[0]["score"] > 0.6

	inbox = await user_client.get(f"/stories/{story_id}/inbox?kind=merge")
	items = inbox.json()["items"]
	assert len(items) == 1
	assert items[0]["kind"] == "merge"
	assert "same thing" in items[0]["title"]
	assert items[0]["actions"] == ["merge", "dismiss"]

	dismissed = await user_client.post(
		f"/stories/{story_id}/inbox/decide",
		json={"ids": [items[0]["id"]], "action": "dismiss"},
	)
	assert dismissed.json()["merges"] == 1
	assert (await user_client.get(f"/stories/{story_id}/inbox?kind=merge")).json()["items"] == []
	# A second load does not resurrect it.
	again = await user_client.get(f"/stories/{story_id}/merge-proposals")
	assert again.json() == []


async def test_accepting_a_merge_proposal_moves_facts(user_client):
	story_id = await _story(user_client)
	chapter = await _chapter(user_client, story_id, "Her eyes were grey.")
	keep = await _entity(user_client, story_id, "Mira Voss")
	gone = await _entity(user_client, story_id, "Mira Vosse")
	fact = await _fact(user_client, gone["id"], chapter["id"], "grey")

	proposals = (await user_client.get(f"/stories/{story_id}/merge-proposals")).json()
	assert len(proposals) == 1
	proposal = proposals[0]
	result = await user_client.post(
		f"/stories/{story_id}/inbox/decide",
		json={"ids": [proposal["id"]], "action": "accept"},
	)
	assert result.json()["merges"] == 1

	# The pair is ordered by id, so the surviving entity is the proposal's target.
	facts = (await user_client.get(f"/entities/{proposal['target_id']}/facts")).json()["facts"]
	assert [row["id"] for row in facts] == [fact["id"]]
	assert {keep["id"], gone["id"]} == {proposal["source_id"], proposal["target_id"]}


async def test_auto_accept_rules_preview_and_run(user_client):
	story_id = await _story(user_client)
	chapter = await _chapter(user_client, story_id, "Her eyes were grey.")
	entity = await _entity(user_client, story_id, "Mira Voss")
	fluent = await _fact(user_client, entity["id"], chapter["id"], "grey", confidence=95)
	unsure = await _fact(user_client, entity["id"], chapter["id"], "green", confidence=55)

	defaults = await user_client.get(f"/stories/{story_id}/inbox/rules")
	assert defaults.json()["min_confidence"] == 80

	preview = await user_client.get(f"/stories/{story_id}/inbox/rules/preview")
	body = preview.json()
	# Nothing is accepted yet, so there is no conflict to block: the 95% proposal
	# qualifies and the 55% one is held by the confidence threshold.
	assert body["would_accept"] == 1
	assert body["held"] == 1

	updated = await user_client.put(
		f"/stories/{story_id}/inbox/rules", json={"min_confidence": 50}
	)
	assert updated.json()["min_confidence"] == 50

	preview = (await user_client.get(f"/stories/{story_id}/inbox/rules/preview")).json()
	assert preview["would_accept"] == 2
	assert preview["held"] == 0

	run = await user_client.post(f"/stories/{story_id}/inbox/auto-accept")
	assert run.json() == {"accepted": 2, "held": 0}

	facts = (await user_client.get(f"/entities/{entity['id']}/facts")).json()["facts"]
	assert {row["status"] for row in facts} == {"accepted"}
	assert {row["id"] for row in facts} == {fluent["id"], unsure["id"]}


async def test_auto_accept_blocks_conflicts_and_respects_the_cap(user_client):
	story_id = await _story(user_client)
	chapter = await _chapter(user_client, story_id, "Her eyes were grey.")
	entity = await _entity(user_client, story_id, "Mira Voss")
	await _fact(user_client, entity["id"], chapter["id"], "grey")
	await _fact(user_client, entity["id"], chapter["id"], "green")

	# Both proposals qualify while nothing is accepted.
	preview = (await user_client.get(f"/stories/{story_id}/inbox/rules/preview")).json()
	assert preview["would_accept"] == 2

	# The per-chapter cap holds the rest back.
	await user_client.put(f"/stories/{story_id}/inbox/rules", json={"max_per_chapter": 1})
	preview = (await user_client.get(f"/stories/{story_id}/inbox/rules/preview")).json()
	assert preview["would_accept"] == 1
	assert preview["held"] == 1

	# With one value accepted, block_conflicts keeps the disagreement out.
	await user_client.put(f"/stories/{story_id}/inbox/rules", json={"max_per_chapter": 20})
	inbox = (await user_client.get(f"/stories/{story_id}/inbox?kind=fact")).json()["items"]
	await user_client.post(
		f"/stories/{story_id}/inbox/decide",
		json={"ids": [inbox[0]["id"]], "action": "accept"},
	)
	preview = (await user_client.get(f"/stories/{story_id}/inbox/rules/preview")).json()
	assert preview["would_accept"] == 0
	assert preview["held"] == 1


async def test_inbox_counts_include_merges(user_client, session):
	story_id = await _story(user_client)
	await _entity(user_client, story_id, "Zephyrion")
	await _entity(user_client, story_id, "Zephyrionn")
	await user_client.get(f"/stories/{story_id}/merge-proposals")

	from app.services import inbox as inbox_service

	async with session.begin():
		pass
	counts = await inbox_service.counts(session, UUID(story_id))
	assert counts["merge"] == 1
	assert counts["total"] == 1
