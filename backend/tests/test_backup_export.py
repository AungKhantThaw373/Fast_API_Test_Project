"""Export files and a full JSON backup round-trip."""

import pytest

from app.services.export import browser_binary, pandoc_binary


async def _story_with_wiki(client):
    story = await client.post("/stories", json={"title": "The Lantern Road"})
    assert story.status_code == 201, story.text
    story_id = story.json()["id"]
    arc = await client.post(f"/stories/{story_id}/arcs", json={"name": "The gate"})
    assert arc.status_code == 201, arc.text
    chapter = await client.post(
        f"/stories/{story_id}/chapters",
        json={
            "title": "The gate",
            "content": "Mira opens the gate.\n\n* * *\n\nThe lantern is already lit.\n",
        },
    )
    assert chapter.status_code == 201, chapter.text
    chapter_row = chapter.json()
    await client.put(
        f"/stories/{story_id}/arcs",
        json={"arc_id": arc.json()["id"], "chapter_ids": [chapter_row["id"]]},
    )
    entity = await client.post(
        f"/stories/{story_id}/entities", json={"name": "Mira Voss", "entity_type": "character"}
    )
    assert entity.status_code == 201, entity.text
    fact = await client.post(
        f"/entities/{entity.json()['id']}/facts",
        json={
            "predicate": "carries",
            "value_text": "a lantern",
            "chapter_id": chapter_row["id"],
            "quote": "The lantern is already lit.",
            "status": "accepted",
        },
    )
    assert fact.status_code == 201, fact.text
    thread = await client.post(
        f"/stories/{story_id}/threads",
        json={
            "title": "Who lit the lantern?",
            "setup_chapter_id": chapter_row["id"],
            "setup_quote": "The lantern is already lit.",
            "linked_entity_ids": [entity.json()["id"]],
        },
    )
    assert thread.status_code == 201, thread.text
    event = await client.post(
        f"/stories/{story_id}/events",
        json={"chapter_id": chapter_row["id"], "summary": "Mira enters the gate." },
    )
    assert event.status_code == 201, event.text
    synopsis = await client.put(
        f"/stories/chapters/{chapter_row['id']}/synopsis",
        json={"synopsis": "Mira finds the gate unlocked."},
    )
    assert synopsis.status_code == 200, synopsis.text
    return story_id, chapter_row, entity.json()


async def test_backup_round_trip_restores_content_and_graph(user_client):
    story_id, chapter, entity = await _story_with_wiki(user_client)
    custom = {
        "version": 1,
        "types": [
            {
                "key": "technique",
                "label": "Technique",
                "sections": {"relationships": False},
                "fields": [{"key": "element", "label": "Element"}],
            }
        ],
    }
    saved_format = await user_client.put(f"/stories/{story_id}/wiki-format", json=custom)
    assert saved_format.status_code == 200, saved_format.text
    exported = await user_client.get(f"/stories/{story_id}/backup")
    assert exported.status_code == 200, exported.text
    data = exported.json()
    assert data["format_version"] == 1
    assert data["story"]["title"] == "The Lantern Road"
    assert data["chapters"][0]["content"].startswith("Mira opens the gate.")
    assert data["entities"][0]["facts"][0]["status"] == "accepted"
    assert data["threads"][0]["title"] == "Who lit the lantern?"
    assert data["chapter_meta"][0]["synopsis"] == "Mira finds the gate unlocked."
    assert data["story"]["wiki_format"]["types"][0]["key"] == "technique"

    restored = await user_client.post("/stories/import-backup", json=data)
    assert restored.status_code == 201, restored.text
    result = restored.json()
    assert result["chapters"] == 1
    assert result["entities"] == 1
    assert result["facts"] == 1
    assert result["threads"] == 1
    assert result["events"] == 1

    new_id = result["story_id"]
    detail = await user_client.get(f"/stories/{new_id}")
    assert detail.status_code == 200
    new_chapter = detail.json()["chapters"][0]
    assert new_chapter["title"] == chapter["title"]
    saved_chapter = await user_client.get(f"/stories/chapters/{new_chapter['id']}")
    assert saved_chapter.status_code == 200
    assert saved_chapter.json()["content"] == chapter["content"]
    entities = await user_client.get(f"/stories/{new_id}/entities")
    assert [row["name"] for row in entities.json()["entities"]] == [entity["name"]]
    facts = await user_client.get(f"/entities/{entities.json()['entities'][0]['id']}/facts")
    assert facts.json()["facts"][0]["predicate"] == "carries"
    threads = await user_client.get(f"/stories/{new_id}/threads")
    assert threads.json()["threads"][0]["setup_chapter_id"] == new_chapter["id"]
    restored_format = await user_client.get(f"/stories/{new_id}/wiki-format")
    assert restored_format.json()["types"][0]["key"] == "technique"


async def test_backup_rejects_unknown_format_version(user_client):
    story_id, _, _ = await _story_with_wiki(user_client)
    data = (await user_client.get(f"/stories/{story_id}/backup")).json()
    data["format_version"] = 99
    response = await user_client.post("/stories/import-backup", json=data)
    assert response.status_code == 422


async def test_backup_and_export_are_owner_only(user_client, make_client):
    story_id, _, _ = await _story_with_wiki(user_client)
    other = await make_client("other", "other@example.com")
    assert (await other.get(f"/stories/{story_id}/backup")).status_code == 404
    assert (await other.get(f"/stories/{story_id}/export?format=markdown")).status_code == 404


@pytest.mark.skipif(pandoc_binary() is None, reason="Pandoc is not installed")
async def test_markdown_docx_and_epub_exports(user_client):
    story_id, _, _ = await _story_with_wiki(user_client)
    markdown = await user_client.get(f"/stories/{story_id}/export?format=markdown")
    assert markdown.status_code == 200
    assert "## Chapter 1: The gate" in markdown.text
    assert "Appendix: Story wiki" in markdown.text
    assert "Mira Voss" in markdown.text
    assert "⁂" in markdown.text
    for fmt, signature in (("docx", b"PK"), ("epub", b"PK")):
        response = await user_client.get(f"/stories/{story_id}/export?format={fmt}")
        assert response.status_code == 200, response.text
        assert response.content.startswith(signature)
        assert len(response.content) > 1000
        assert fmt in response.headers["content-disposition"]


@pytest.mark.skipif(
    pandoc_binary() is None or browser_binary() is None, reason="Pandoc or a browser is unavailable"
)
async def test_pdf_export(user_client):
    story_id, _, _ = await _story_with_wiki(user_client)
    response = await user_client.get(f"/stories/{story_id}/export?format=pdf")
    assert response.status_code == 200, response.text
    assert response.content.startswith(b"%PDF")
    assert len(response.content) > 5000