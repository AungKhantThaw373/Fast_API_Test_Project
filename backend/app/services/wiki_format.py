"""Per-story wiki format.

A story bible is not one shape. A character has relationships; a place usually
does not. Some novels need a "technique" card with a cost and an element; others
need nothing but a summary. This module owns the default skeleton and the
resolved format used by both the API and extraction.

The format is deliberately data, not code. Entry types are labels over the
existing entity_type slug, custom fields are suggestions over the existing
fact predicate vocabulary, and every section can be turned off without deleting
the underlying rows. Sources and provenance are untouched.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import ValidationError

from app.schemas.wiki_format import WikiFormat

WIKI_SECTIONS = ("summary", "facts", "relationships", "aliases", "appearances", "threads")

_ALL_SECTIONS = {section: True for section in WIKI_SECTIONS}


def _sections(*disabled: str) -> dict[str, bool]:
    values = dict(_ALL_SECTIONS)
    for section in disabled:
        values[section] = False
    return values


_DEFAULT: dict[str, Any] = {
    "version": 1,
    "types": [
        {
            "key": "character",
            "label": "Character",
            "description": "People, spirits, or narrators with agency.",
            "sections": _sections(),
            "fields": [
                {"key": "role", "label": "Role", "hint": "What they do in the story"},
                {"key": "age", "label": "Age", "hint": "Age or apparent age"},
                {"key": "affiliation", "label": "Affiliation", "hint": "Group, house, or loyalty"},
                {"key": "goal", "label": "Goal", "hint": "What they are trying to get"},
                {"key": "secret", "label": "Secret", "hint": "What they hide"},
            ],
        },
        {
            "key": "location",
            "label": "Place",
            "description": "A location, realm, or room that can hold a scene.",
            "sections": _sections("relationships"),
            "fields": [
                {"key": "region", "label": "Region", "hint": "Where it sits in the world"},
                {"key": "population", "label": "Population", "hint": "Size or people"},
                {"key": "atmosphere", "label": "Atmosphere", "hint": "What it feels like"},
            ],
        },
        {
            "key": "item",
            "label": "Item",
            "description": "An object that matters to the plot.",
            "sections": _sections("relationships"),
            "fields": [
                {"key": "owner", "label": "Owner", "hint": "Who holds it now"},
                {"key": "origin", "label": "Origin", "hint": "Where it came from"},
                {"key": "ability", "label": "Ability", "hint": "What it does"},
            ],
        },
        {
            "key": "organization",
            "label": "Group",
            "description": "A faction, family, order, or institution.",
            "sections": _sections("relationships"),
            "fields": [
                {"key": "purpose", "label": "Purpose", "hint": "What it exists to do"},
                {"key": "headquarters", "label": "Headquarters", "hint": "Where it is based"},
                {"key": "membership", "label": "Membership", "hint": "Who belongs"},
            ],
        },
        {
            "key": "concept",
            "label": "Concept",
            "description": "An idea, title, event, or piece of history.",
            "sections": _sections("relationships", "aliases"),
            "fields": [
                {"key": "domain", "label": "Domain", "hint": "Where it applies"},
                {"key": "meaning", "label": "Meaning", "hint": "What it means in this story"},
            ],
        },
        {
            "key": "world_rule",
            "label": "World rule",
            "description": "A law of the world that constrains the story.",
            "sections": _sections("relationships", "aliases"),
            "fields": [
                {"key": "scope", "label": "Scope", "hint": "Who or what it governs"},
                {"key": "consequence", "label": "Consequence", "hint": "What happens when it breaks"},
            ],
        },
        {
            "key": "power_system",
            "label": "Power system",
            "description": "A system of magic, technology, or ability.",
            "sections": _sections("relationships"),
            "fields": [
                {"key": "source", "label": "Source", "hint": "Where the power comes from"},
                {"key": "cost", "label": "Cost", "hint": "What using it takes"},
                {"key": "limit", "label": "Limit", "hint": "What it cannot do"},
            ],
        },
        {
            "key": "creature",
            "label": "Creature",
            "description": "A non-human being or species.",
            "sections": _sections("relationships"),
            "fields": [
                {"key": "habitat", "label": "Habitat", "hint": "Where it lives"},
                {"key": "danger", "label": "Danger", "hint": "How it threatens the story"},
            ],
        },
        {
            "key": "other",
            "label": "Other",
            "description": "Anything the story needs that is not above.",
            "sections": _sections("relationships", "aliases"),
            "fields": [],
        },
    ],
}


def default_wiki_format() -> dict[str, Any]:
    return deepcopy(_DEFAULT)


def resolve_wiki_format(raw: Any) -> dict[str, Any]:
    """Return a valid format, falling back to the default skeleton.

    Older stories have no stored format. A malformed stored value should not
    break the wiki, so the default is a safe read path; the write endpoint
    validates before saving.
    """
    if not isinstance(raw, dict):
        return default_wiki_format()
    try:
        return WikiFormat.model_validate(raw).model_dump()
    except ValidationError:
        return default_wiki_format()


def type_keys(format_data: dict[str, Any]) -> list[str]:
    return [str(item["key"]) for item in format_data.get("types", []) if item.get("key")]


def type_map(format_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item["key"]): item
        for item in format_data.get("types", [])
        if isinstance(item, dict) and item.get("key")
    }


def relationship_allowed(format_data: dict[str, Any], entity_type: str) -> bool:
    item = type_map(format_data).get(entity_type)
    if item is None:
        return True
    sections = item.get("sections")
    if not isinstance(sections, dict):
        return True
    return bool(sections.get("relationships", True))
