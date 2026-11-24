"""Knowledge model: normalization, candidates, mentions, merge, and backfill."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.backfill.bible import backfill_story, locate_quote
from app.models.story_models import Chapter, Story, StoryBibleEntry
from app.models.wiki_models import (
    Entity,
    EntityAlias,
    EntityFact,
    EntityMention,
    EntityRelationship,
    StoryThread,
)
from app.services import entities as entity_service


async def _story(session, client, title="Wiki") -> Story:
    owner = UUID((await client.get("/me")).json()["id"])
    story = Story(owner_id=owner, title=title)
    session.add(story)
    await session.commit()
    return story


async def _chapter(session, story: Story, number: int, content: str) -> Chapter:
    chapter = Chapter(
        story_id=story.id,
        chapter_number=number,
        position=number * 1024.0,
        title=f"Chapter {number}",
        content=content,
        word_count=len(content.split()),
        revision=1,
        index_status="indexed",
    )
    session.add(chapter)
    await session.commit()
    return chapter


def test_normalization_collapses_case_spacing_and_honorifics():
    assert entity_service.normalize_name("Mira") == "mira"
    assert entity_service.normalize_name("  MIRA  ") == "mira"
    assert entity_service.normalize_name("\uff2d\uff49\uff52\uff41") == "mira"  # NFKC wide letters
    assert entity_service.normalize_name("Lady Voss") == "voss"
    # Honorifics are stripped for resolution; the raw alias still matches text.
    assert entity_service.normalize_name("the captain") == ""
    assert entity_service.normalize_name("Kael\u2019s") == entity_service.normalize_name("Kael’s")


def test_locate_quote_returns_line_numbers():
    content = "First line.\nSecond line has Mira.\nThird."
    assert locate_quote(content, "Mira") == (2, 2)
    assert locate_quote(content, "no such text") == (None, None)


async def test_exact_alias_match_beats_similarity(user_client, session):
    story = await _story(session, user_client)
    await entity_service.create_entity(
        session, story_id=story.id, entity_type="character", name="Mira Voss"
    )
    await entity_service.create_entity(
        session, story_id=story.id, entity_type="character", name="Mira Volst"
    )
    await session.commit()

    candidates = await entity_service.find_candidates(session, story.id, "mira voss")
    assert candidates
    assert candidates[0].score == 1.0
    assert candidates[0].entity.name == "Mira Voss"


async def test_fuzzy_candidate_is_proposed_but_not_created(user_client, session):
    story = await _story(session, user_client)
    await entity_service.create_entity(
        session, story_id=story.id, entity_type="character", name="Zephyrion"
    )
    await session.commit()

    candidates = await entity_service.find_candidates(session, story.id, "Zephyrionn")
    assert candidates
    assert 0.5 < candidates[0].score < 1.0
    # Looking does not write anything.
    assert (
        await session.scalar(
            select(Entity).where(Entity.canonical_name == "zephyrionn")
        )
    ) is None


async def test_mention_extraction_is_case_insensitive_and_range_limited(
    user_client, session
):
    story = await _story(session, user_client)
    mira = await entity_service.create_entity(
        session,
        story_id=story.id,
        entity_type="character",
        name="Mira Voss",
        aliases=[("Mira", "name"), ("the captain", "title")],
    )
    await session.commit()
    chapter = await _chapter(
        session,
        story,
        1,
        "Mira walked in.\nThe captain said nothing.\nA mirage shimmered.\n",
    )

    count = await entity_service.extract_mentions(session, story.id, chapter.id, chapter.content)
    await session.commit()

    mentions = list(
        await session.scalars(select(EntityMention).where(EntityMention.chapter_id == chapter.id))
    )
    assert count == len(mentions) == 2
    assert sorted(item.line_start for item in mentions) == [1, 2]
    # "mirage" must not match "Mira".
    assert all("mirage" not in item.quote.lower() for item in mentions)

    refreshed = await session.get(Entity, mira.id)
    assert refreshed is not None
    assert refreshed.first_chapter_number == 1
    assert refreshed.last_chapter_number == 1


async def test_merge_moves_everything_and_can_be_dry_run(user_client, session):
    story = await _story(session, user_client)
    story_id = story.id
    source = await entity_service.create_entity(
        session, story_id=story_id, entity_type="character", name="Mira Voss"
    )
    target = await entity_service.create_entity(
        session,
        story_id=story.id,
        entity_type="character",
        name="Mira",
        aliases=[("Lady Voss", "title")],
    )
    chapter = await _chapter(session, story, 1, "Mira Voss spoke to Lady Voss.")
    session.add(
        EntityFact(
            entity_id=source.id,
            predicate="eye_color",
            value_text="grey",
            quote="Mira Voss",
            chapter_id=chapter.id,
            status="accepted",
        )
    )
    session.add(
        EntityMention(
            entity_id=source.id,
            chapter_id=chapter.id,
            line_start=1,
            line_end=1,
            quote="Mira Voss spoke to Lady Voss.",
        )
    )
    session.add(
        EntityRelationship(
            story_id=story.id,
            from_entity_id=source.id,
            to_entity_id=target.id,
            relationship_type="sibling_of",
        )
    )
    await session.commit()

    source_id, target_id = source.id, target.id
    dry = await entity_service.merge_entities(
        session, story_id=story_id, source_id=source_id, target_id=target_id, dry_run=True
    )
    assert dry["facts"] == 1 and dry["mentions"] == 1 and dry["relationships"] == 1
    await session.rollback()
    # A dry run changes nothing. (Rollback expires ORM objects, so compare by id.)
    assert (
        await session.scalar(select(EntityFact).where(EntityFact.entity_id == source_id))
    ) is not None

    moved = await entity_service.merge_entities(
        session, story_id=story_id, source_id=source_id, target_id=target_id
    )
    await session.commit()
    assert moved["facts"] == 1

    merged = await session.get(Entity, source.id)
    assert merged is not None
    assert merged.merged_into_id == target.id
    assert merged.status == "merged"

    facts = list(await session.scalars(select(EntityFact)))
    assert [fact.entity_id for fact in facts] == [target.id]
    mentions = list(await session.scalars(select(EntityMention)))
    assert [mention.entity_id for mention in mentions] == [target.id]
    aliases = {
        alias.normalized_alias
        for alias in await session.scalars(
            select(EntityAlias).where(EntityAlias.entity_id == target.id)
        )
    }
    assert {"mira", "voss"} <= aliases

    # The merged-away id still resolves to the live entity.
    resolved = await entity_service.resolve_entity(session, source.id)
    assert resolved is not None
    assert resolved.id == target.id


async def test_merge_guards(user_client, session):
    story = await _story(session, user_client)
    other_story = await _story(session, user_client, "Other")
    left = await entity_service.create_entity(
        session, story_id=story.id, entity_type="character", name="Left"
    )
    right = await entity_service.create_entity(
        session, story_id=story.id, entity_type="character", name="Right"
    )
    foreign = await entity_service.create_entity(
        session, story_id=other_story.id, entity_type="character", name="Foreign"
    )
    await session.commit()

    with pytest.raises(Exception) as self_merge:
        await entity_service.merge_entities(
            session, story_id=story.id, source_id=left.id, target_id=left.id
        )
    assert getattr(self_merge.value, "status_code", None) == 422

    with pytest.raises(Exception) as cross_story:
        await entity_service.merge_entities(
            session, story_id=story.id, source_id=left.id, target_id=foreign.id
        )
    assert getattr(cross_story.value, "status_code", None) == 422

    await entity_service.merge_entities(
        session, story_id=story.id, source_id=left.id, target_id=right.id
    )
    await session.commit()
    with pytest.raises(Exception) as already_merged:
        await entity_service.merge_entities(
            session, story_id=story.id, source_id=left.id, target_id=right.id
        )
    assert getattr(already_merged.value, "status_code", None) == 409


async def test_backfill_preserves_ids_and_is_idempotent(user_client, session):
    story = await _story(session, user_client, "Backfill")
    chapter = await _chapter(
        session, story, 1, "Mira Voss has grey eyes.\nThe Night Watch keeps the gate.\n"
    )
    character_id = uuid4()
    thread_id = uuid4()
    session.add_all(
        [
            StoryBibleEntry(
                id=character_id,
                story_id=story.id,
                category="character",
                name="Mira Voss",
                canonical_name="mira voss",
                description="A captain.",
                status="suggested",
                confidence=82,
                source_chapter_id=chapter.id,
                source_quote="Mira Voss has grey eyes.",
            ),
            StoryBibleEntry(
                id=thread_id,
                story_id=story.id,
                category="plot_thread",
                name="Who betrayed the Night Watch?",
                canonical_name="who betrayed the night watch?",
                description="Unresolved.",
                status="accepted",
                thread_state="open",
                confidence=70,
                source_chapter_id=chapter.id,
                source_quote="The Night Watch keeps the gate.",
            ),
        ]
    )
    await session.commit()

    first = await backfill_story(session, story.id, mentions=True)
    assert first["entities"] == 1
    # The plot thread becomes a thread, not an entity, so it has no fact.
    assert first["facts"] == 1
    assert first["threads"] == 1
    assert first["mentions"] >= 1

    entity = await session.get(Entity, character_id)
    assert entity is not None
    assert entity.entity_type == "character"
    assert entity.summary == "A captain."

    facts = list(
        await session.scalars(select(EntityFact).where(EntityFact.entity_id == character_id))
    )
    assert len(facts) == 1
    assert facts[0].status == "proposed"  # suggested maps to proposed
    assert facts[0].confidence == 82
    assert facts[0].line_start == 1
    assert facts[0].created_by == "ai"

    threads = list(await session.scalars(select(StoryThread)))
    assert len(threads) == 1
    assert threads[0].state == "open"
    assert threads[0].story_id == story.id

    second = await backfill_story(session, story.id, mentions=True)
    assert second["entities"] == 0
    assert second["entities_skipped"] == 1
    assert second["facts"] == 0
    assert second["threads"] == 0
    assert len(list(await session.scalars(select(EntityFact)))) == 1
    assert len(list(await session.scalars(select(StoryThread)))) == 1
