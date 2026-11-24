"""Zero-token name candidates: heuristics, known names, and acceptance."""

from uuid import UUID

from sqlalchemy import select

from app.services.name_candidates import find_name_candidates

CONTENT = """Before dawn Mira Voss crossed the yard.
The gate creaked. Mira Voss did not look back at the gate.
By the lantern light Tessa waited near the Hollow Gate.
Nobody spoke, and Tessa watched the Hollow Gate stay shut.
"""


def test_capitalised_repeats_become_candidates():
    candidates = find_name_candidates(CONTENT, known=set())
    names = [item.name for item in candidates]
    assert "Mira Voss" in names
    assert "Tessa" in names
    # A repeated pair wins over its halves.
    assert "Mira" not in names
    assert "Tessa" in names
    assert "Hollow Gate" in names


def test_sentence_initial_capitals_are_not_candidates():
    once = "Tessa waited.\nNobody came.\nTessa left."
    candidates = find_name_candidates(once, known=set())
    # "Tessa" is only ever sentence-initial here, so it is grammar, not evidence.
    assert candidates == []


def test_known_aliases_and_common_words_are_skipped():
    candidates = find_name_candidates(CONTENT, known={"mira voss", "tessa", "hollow gate"})
    assert candidates == []

    prose = "The wind rose. The gate shook. The wind fell."
    assert find_name_candidates(prose, known=set()) == []


def test_repeated_single_names_are_reported_with_sample_and_line():
    content = "She met Tessa at noon. At dusk she found Tessa waiting."
    candidates = find_name_candidates(content, known=set())
    assert [item.name for item in candidates] == ["Tessa"]
    assert candidates[0].count == 2
    assert candidates[0].first_line == 1
    assert "Tessa" in candidates[0].sample


async def test_candidate_endpoint_and_acceptance(user_client, session):
    from app.models.story_models import Chapter, Story
    from app.models.wiki_models import Entity, EntityAlias, EntityMention

    owner = UUID((await user_client.get("/me")).json()["id"])
    story = Story(owner_id=owner, title="Candidates")
    session.add(story)
    await session.commit()
    chapter = Chapter(
        story_id=story.id,
        chapter_number=1,
        position=1024.0,
        title="One",
        content="Mira Voss crossed the yard. Later Mira Voss returned to the gate with Tessa.",
        word_count=12,
        revision=1,
        index_status="indexed",
    )
    session.add(chapter)
    await session.commit()

    listed = await user_client.get(
        f"/stories/{story.id}/chapters/{chapter.id}/name-candidates"
    )
    assert listed.status_code == 200, listed.text
    names = [item["name"] for item in listed.json()["candidates"]]
    assert "Mira Voss" in names

    accepted = await user_client.post(
        f"/stories/{story.id}/name-candidates/accept",
        json={
            "name": "Tessa",
            "entity_type": "character",
            "chapter_id": str(chapter.id),
            "quote": "Later Mira Voss returned to the gate with Tessa.",
        },
    )
    assert accepted.status_code == 201, accepted.text
    body = accepted.json()
    assert body["name"] == "Tessa"
    assert {alias["alias"] for alias in body["aliases"]} == {"Tessa"}

    entity = await session.get(Entity, UUID(body["id"]))
    assert entity is not None
    mentions = list(await session.scalars(select(EntityMention)))
    assert len(mentions) == 1
    assert mentions[0].line_start == 1
    aliases = list(await session.scalars(select(EntityAlias)))
    assert [alias.alias for alias in aliases] == ["Tessa"]

    # The accepted name stops being proposed.
    again = await user_client.get(
        f"/stories/{story.id}/chapters/{chapter.id}/name-candidates"
    )
    assert "Tessa" not in [item["name"] for item in again.json()["candidates"]]
