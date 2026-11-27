"""Per-story wiki format: defaults, custom shapes, reset, and ownership."""

from app.services.extraction import extraction_schema, format_prompt
from app.services.wiki_format import relationship_allowed, resolve_wiki_format


async def _story(client, title: str = "Format story") -> str:
    response = await client.post("/stories", json={"title": title})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def test_default_format_has_character_relationships_and_place_without(user_client):
    story_id = await _story(user_client)
    response = await user_client.get(f"/stories/{story_id}/wiki-format")
    assert response.status_code == 200, response.text
    body = response.json()
    by_key = {item["key"]: item for item in body["types"]}
    assert by_key["character"]["sections"]["relationships"] is True
    assert by_key["location"]["sections"]["relationships"] is False
    assert any(field["key"] == "role" for field in by_key["character"]["fields"])


async def test_custom_format_round_trips_and_can_be_reset(user_client):
    story_id = await _story(user_client)
    custom = {
        "version": 1,
        "types": [
            {
                "key": "technique",
                "label": "Technique",
                "description": "A named move with a cost.",
                "sections": {
                    "summary": True,
                    "facts": True,
                    "relationships": False,
                    "aliases": False,
                    "appearances": True,
                    "threads": False,
                },
                "fields": [
                    {"key": "element", "label": "Element", "hint": "What it is made of"},
                ],
            }
        ],
    }
    saved = await user_client.put(f"/stories/{story_id}/wiki-format", json=custom)
    assert saved.status_code == 200, saved.text
    assert saved.json()["types"][0]["label"] == "Technique"

    loaded = await user_client.get(f"/stories/{story_id}/wiki-format")
    assert loaded.json() == saved.json()

    reset = await user_client.delete(f"/stories/{story_id}/wiki-format")
    assert reset.status_code == 200, reset.text
    assert any(item["key"] == "character" for item in reset.json()["types"])


async def test_format_rejects_duplicate_type_keys(user_client):
    story_id = await _story(user_client)
    response = await user_client.put(
        f"/stories/{story_id}/wiki-format",
        json={
            "version": 1,
            "types": [
                {"key": "character", "label": "Character"},
                {"key": "character", "label": "Person"},
            ],
        },
    )
    assert response.status_code == 422


async def test_format_is_owned_by_the_story_owner(user_client, make_client):
    story_id = await _story(user_client)
    other = await make_client("other", "other@example.com")
    response = await other.get(f"/stories/{story_id}/wiki-format")
    assert response.status_code == 404


def test_malformed_or_missing_format_falls_back_to_the_default():
    for raw in (None, "nonsense", {"types": []}, {"types": "nope"}, {"version": 99, "types": []}):
        resolved = resolve_wiki_format(raw)
        assert any(item["key"] == "character" for item in resolved["types"])


def test_relationships_default_on_for_unknown_types_and_follow_the_format():
    data = resolve_wiki_format(
        {"version": 1, "types": [{"key": "place", "label": "Place", "sections": {"relationships": False}}]}
    )
    assert relationship_allowed(data, "place") is False
    assert relationship_allowed(data, "character") is True


def test_format_teaches_extraction_custom_types_and_fields():
    data = resolve_wiki_format(
        {
            "version": 1,
            "types": [
                {
                    "key": "technique",
                    "label": "Technique",
                    "description": "A named move with a cost.",
                    "sections": {"relationships": False},
                    "fields": [{"key": "element", "label": "Element", "hint": "What it is made of"}],
                }
            ],
        }
    )
    prompt = format_prompt(data)
    assert "technique (Technique)" in prompt
    assert "element (Element)" in prompt
    schema = extraction_schema(["technique"])
    assert schema["properties"]["entities"]["items"]["properties"]["entity_type"]["enum"] == [
        "technique"
    ]
