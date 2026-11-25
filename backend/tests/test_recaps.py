"""Recaps: chapter synopses, arc summaries, and Story so far."""



async def _story(client, title="Recaps") -> str:
    response = await client.post("/stories", json={"title": title})
    assert response.status_code == 201
    return response.json()["id"]


async def _chapter(client, story_id: str, number: int, content: str = "") -> dict:
    response = await client.post(
        f"/stories/{story_id}/chapters",
        json={"title": f"Chapter {number}", "content": content or f"Chapter {number} opens the gate."},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_chapter_synopsis_is_generated_then_editable(user_client):
    story_id = await _story(user_client)
    chapter = await _chapter(
        user_client,
        story_id,
        1,
        (
            "Mira Voss crossed the yard. Rain followed her. The gate was locked, "
            "but she had the key. Inside, a lamp burned."
        ),
    )

    generated = await user_client.get(f"/stories/chapters/{chapter['id']}/synopsis")
    assert generated.status_code == 200
    payload = generated.json()
    assert payload["generated"] is True
    assert payload["editable"] is True
    assert "Mira Voss crossed the yard" in payload["synopsis"]

    edited = await user_client.put(
        f"/stories/chapters/{chapter['id']}/synopsis",
        json={"synopsis": "Mira enters the locked gatehouse and finds a lamp already burning."},
    )
    assert edited.status_code == 200
    assert edited.json()["generated"] is False
    assert edited.json()["synopsis"].startswith("Mira enters")

    reread = (await user_client.get(f"/stories/chapters/{chapter['id']}/synopsis")).json()
    assert reread["synopsis"] == edited.json()["synopsis"]
    assert reread["generated"] is False

    # Generation is explicit; it does not quietly replace an edited synopsis.
    kept = await user_client.post(f"/stories/chapters/{chapter['id']}/synopsis/generate")
    assert kept.json()["synopsis"] == edited.json()["synopsis"]
    replaced = await user_client.post(
        f"/stories/chapters/{chapter['id']}/synopsis/generate?overwrite=true"
    )
    assert replaced.json()["generated"] is True
    assert replaced.json()["synopsis"] != edited.json()["synopsis"]


async def test_arc_summary_is_built_from_chapter_synopses(user_client):
    story_id = await _story(user_client)
    first = await _chapter(user_client, story_id, 1)
    second = await _chapter(user_client, story_id, 2)
    arc = (await user_client.post(f"/stories/{story_id}/arcs", json={"name": "The gate"})).json()
    assigned = await user_client.put(
        f"/stories/{story_id}/arcs",
        json={"arc_id": arc["id"], "chapter_ids": [first["id"], second["id"]]},
    )
    assert assigned.json()["updated"] == 2
    await user_client.put(
        f"/stories/chapters/{first['id']}/synopsis",
        json={"synopsis": "Mira opens the gate."},
    )

    generated = await user_client.post(
        f"/stories/{story_id}/arcs/{arc['id']}/summary/generate"
    )
    assert generated.status_code == 200, generated.text
    payload = generated.json()
    assert payload["chapter_count"] == 2
    assert "Mira opens the gate." in payload["summary"]
    assert "Chapter 1" in payload["summary"]
    assert "Chapter 2" in payload["summary"]

    listed = (await user_client.get(f"/stories/{story_id}/arcs")).json()
    assert listed[0]["summary"] == payload["summary"]


async def test_story_so_far_returns_recent_chapters_with_citations(user_client):
    story_id = await _story(user_client)
    for number in range(1, 8):
        await _chapter(user_client, story_id, number, f"Chapter {number} begins with a lantern.")

    response = await user_client.get(f"/stories/{story_id}/recap?limit=3")
    assert response.status_code == 200
    payload = response.json()
    assert payload["read_only"] is True
    assert [row["chapter_number"] for row in payload["chapters"]] == [5, 6, 7]
    assert payload["range_label"] == "Chapters 5–7"
    citation = payload["chapters"][0]["citation"]
    assert citation["chapter_number"] == 5
    assert citation["line"] == 1
    assert "Chapter 5 begins" in citation["quote"]
    assert payload["chapters"][0]["synopsis"]


async def test_story_so_far_can_scope_to_an_arc(user_client):
    story_id = await _story(user_client)
    chapters = [await _chapter(user_client, story_id, number) for number in range(1, 4)]
    arc = (await user_client.post(f"/stories/{story_id}/arcs", json={"name": "One arc"})).json()
    await user_client.put(
        f"/stories/{story_id}/arcs",
        json={"arc_id": arc["id"], "chapter_ids": [chapters[0]["id"], chapters[1]["id"]]},
    )

    response = await user_client.get(f"/stories/{story_id}/recap?arc_id={arc['id']}")
    assert response.status_code == 200
    payload = response.json()
    assert [row["chapter_number"] for row in payload["chapters"]] == [1, 2]
    assert payload["arcs"][0]["arc_id"] == arc["id"]


async def test_empty_chapter_cannot_be_summarized(user_client):
    story_id = await _story(user_client)
    chapter = await _chapter(user_client, story_id, 1, "")
    # _chapter fills empty content, so create an explicitly blank chapter.
    blank = await user_client.post(
        f"/stories/{story_id}/chapters", json={"title": "Blank", "content": ""}
    )
    response = await user_client.post(f"/stories/chapters/{blank.json()['id']}/synopsis/generate")
    assert response.status_code == 409
    assert chapter["id"]


async def test_recap_endpoints_are_owner_scoped(make_client):
    alice = await make_client("recap-alice", "recap-alice@example.com")
    bob = await make_client("recap-bob", "recap-bob@example.com")
    story_id = await _story(alice)
    chapter = await _chapter(alice, story_id, 1)
    arc = (await alice.post(f"/stories/{story_id}/arcs", json={"name": "Mine"})).json()

    assert (await bob.get(f"/stories/chapters/{chapter['id']}/synopsis")).status_code == 404
    assert (
        await bob.put(
            f"/stories/chapters/{chapter['id']}/synopsis", json={"synopsis": "stolen"}
        )
    ).status_code == 404
    assert (
        await bob.post(f"/stories/chapters/{chapter['id']}/synopsis/generate" )
    ).status_code == 404
    assert (
        await bob.post(f"/stories/{story_id}/arcs/{arc['id']}/summary/generate")
    ).status_code == 404
    assert (await bob.get(f"/stories/{story_id}/recap")).status_code == 404

    # The owner still sees all of it.
    assert (await alice.get(f"/stories/chapters/{chapter['id']}/synopsis")).status_code == 200
    assert (await alice.get(f"/stories/{story_id}/recap")).status_code == 200