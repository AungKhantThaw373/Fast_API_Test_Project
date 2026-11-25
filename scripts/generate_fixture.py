"""Generate a deterministic synthetic serial for scale testing.

Usage (from the repository root):

    python scripts/generate_fixture.py
    python scripts/generate_fixture.py --chapters 1100 --words 900 --out data/scale-fixture

The output is deliberately text-only and contains no copyrighted material. It
writes chapters.jsonl, entities.json, threads.json, contradictions.json and
manifest.json. The real database is never touched.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

FIRST_A = ["Ar", "Bel", "Cor", "Dar", "El", "Fen", "Gar", "Hal", "Ish", "Jor",
           "Kae", "Lor", "Mar", "Ner", "Or", "Per", "Quin", "Rav", "Sel", "Tor",
           "Ul", "Vey", "Wren", "Xan", "Yor", "Zel", "Bran", "Cael", "Dren", "Esk"]
FIRST_B = ["a", "en", "ric", "da", "wen", "is", "or", "ael", "in", "eth",
           "ara", "ion", "us", "elle", "an", "ir", "ona", "eth", "ur", "ai"]
LAST_A = ["Voss", "Holt", "Mere", "Quay", "Rook", "Sable", "Thorne", "Wilde",
          "Ash", "Briar", "Cole", "Dane", "Elder", "Frost", "Gale", "Hale",
          "Ives", "Jade", "Kerr", "Lark", "Moss", "North", "Oakes", "Pike", "Reed"]
LAST_B = ["", "e", "wood", "field", "stone", "well", "ford", "ridge", "brook", "crest", "mere", "shore"]
PLACE_A = ["Ashen", "Bitter", "Cobalt", "Dawn", "Ember", "Fallow", "Grey", "Hollow",
           "Iron", "Jade", "Kestrel", "Lantern", "Mist", "North", "Old"]
PLACE_B = ["Harbour", "Quay", "Abbey", "Bridge", "Market", "Gate", "Moor", "Vale",
           "Reach", "Crossing"]
ITEM_A = ["brass", "cracked", "silver", "salt-stained", "carved", "black", "woven",
          "iron", "glass", "leather", "bone", "red", "quiet", "broken", "gilded",
          "cold", "narrow", "bright", "empty", "old"]
ITEM_B = ["ledger", "compass", "lantern", "bell", "chart", "key", "ring", "blade",
          "cup", "letter"]
ORG_A = ["Grey", "Salt", "Lantern", "Iron", "Quiet",
         "Broken", "Northern", "Old", "Jade", "Hollow"]
ORG_B = ["Council", "Watch", "Guild", "Order", "Company", "House", "Circle",
         "Choir", "Court", "Assembly"]
ALIAS_ADJ = ["grey", "salt", "quiet", "iron", "lantern", "northern", "hollow",
             "jade", "bitter", "dawn", "ember", "winter", "storm", "ash", "gold"]
ALIAS_ROLE = ["warden", "keeper", "navigator", "scribe", "hunter", "smith",
              "captain", "healer", "envoy", "archivist", "ferryman", "lookout",
              "gardener", "cook", "quartermaster", "cartographer", "singer",
              "watchman", "trader", "pilot"]

VERBS = ["counted", "carried", "mended", "questioned", "followed", "left", "found",
         "hid", "traded", "watched", "mapped", "weighed", "copied", "buried",
         "polished", "measured", "named", "forgot", "promised", "returned"]
OBJECTS = ["ledger", "chart", "rope", "bell", "compass", "letter", "coat", "lantern",
           "boat", "key", "map", "cup", "knife", "coin", "bottle", "satchel"]
ADJECTIVES = ["grey", "salt-stained", "quiet", "broken", "borrowed", "cold",
              "narrow", "bright", "empty", "old", "rain-dark", "wind-worn"]

TRAITS = [
    ("scar", "had a pale scar on the left hand", "had no scar on the left hand",
     "had a scar on the right hand", "different hand"),
    ("eyes", "had grey eyes", "had green eyes",
     "had grey eyes in one light and green in another", "unreliable observation"),
    ("birthplace", "was born in {place}", "was born in {other_place}",
     "was raised in {other_place}", "raised, not born, there"),
    ("sword", "carried a sword named {item}", "carried a sword named {other_item}",
     "carried a dagger named {item}", "different weapon"),
    ("height", "was tall", "was short",
     "seemed tall beside the child", "relative comparison"),
]


def _unique_names() -> list[str]:
    names = []
    for first in FIRST_A:
        for second in FIRST_B:
            names.append(first + second)
    return names[:300]


def _unique_last_names() -> list[str]:
    names = []
    for first in LAST_A:
        for second in LAST_B:
            names.append(first + second)
    return names[:300]


def _entities() -> dict:
    first_names = _unique_names()
    last_names = _unique_last_names()
    characters = []
    for index, first in enumerate(first_names):
        last = last_names[index]
        alias = f"the {ALIAS_ADJ[index % len(ALIAS_ADJ)]} {ALIAS_ROLE[index % len(ALIAS_ROLE)]}"
        characters.append({
            "type": "character",
            "name": f"{first} {last}",
            "aliases": [first, last, alias],
            "summary": (
                f"A recurring {ALIAS_ROLE[index % len(ALIAS_ROLE)]} from the "
                f"{PLACE_A[index % len(PLACE_A)]} {PLACE_B[index % len(PLACE_B)]}."
            ),
        })
    locations = [
        {"type": "location", "name": f"{a} {b}", "aliases": [b],
         "summary": f"A {b.lower()} on the {a.lower()} coast."}
        for a in PLACE_A for b in PLACE_B
    ][:150]
    items = [
        {"type": "item", "name": f"{a} {b}", "aliases": [b],
         "summary": f"A {a} {b} that changes hands."}
        for a in ITEM_A for b in ITEM_B
    ][:200]
    organizations = [
        {"type": "organization", "name": f"{a} {b}", "aliases": [b],
         "summary": f"{b} of the {a.lower()} coast."}
        for a in ORG_A for b in ORG_B
    ][:100]
    return {"characters": characters, "locations": locations,
            "items": items, "organizations": organizations}


def _sentence(rng: random.Random, ch: dict, loc: dict, item: dict, org: dict) -> str:
    template = rng.choice([
        "{ch} {verb} the {adj} {obj} near the {loc}, and {org} kept the record.",
        "{ch} asked about the {adj} {obj} while the {org} watched the {loc}.",
        "At the {loc}, {ch} met a {role} who carried a {adj} {obj}.",
        "The {org} sent {ch} to the {loc} with a {adj} {obj} and no map.",
        "{ch} said the {obj} was {adj}; the {org} disagreed and the {loc} went quiet.",
        "Rain crossed the {loc} while {ch} counted every {adj} {obj}.",
        "{ch} remembered a {role} from the {org} and the {adj} {obj} they left behind.",
        "No one at the {loc} could explain why the {org} wanted the {obj}.",
        "{ch} traded the {adj} {obj} for a place beside the {loc} fire.",
        "The {loc} bell rang twice; {ch} and the {org} stopped to listen.",
        "{ch} drew the {loc} from memory, marking the {obj} and the {org} hall.",
        "A {role} from the {org} told {ch} that the {obj} had been moved before dawn.",
    ])
    return template.format(
        ch=ch["name"], loc=loc["name"].lower(), item=item["name"],
        org=org["name"], verb=rng.choice(VERBS), adj=rng.choice(ADJECTIVES),
        obj=rng.choice(OBJECTS), role=rng.choice(ALIAS_ROLE),
    )


def _paragraph(rng: random.Random, ch: dict, loc: dict, item: dict, org: dict,
               target_words: int) -> str:
    sentences = []
    words = 0
    while words < target_words:
        sentence = _sentence(rng, ch, loc, item, org)
        sentences.append(sentence)
        words += len(sentence.split())
    return " ".join(sentences)


def _contradiction_text(entities: dict, chapter_number: int, index: int,
                        chapter_total: int) -> dict:
    characters = entities["characters"]
    places = entities["locations"]
    items = entities["items"]
    character = characters[index % len(characters)]
    trait = TRAITS[index % len(TRAITS)]
    predicate, canonical, contradiction, near, reason = trait
    place = places[(index * 3) % len(places)]["name"]
    other_place = places[(index * 3 + 7) % len(places)]["name"]
    item = items[(index * 5) % len(items)]["name"]
    other_item = items[(index * 5 + 11) % len(items)]["name"]
    canonical = canonical.format(place=place, other_place=other_place,
                                  item=item, other_item=other_item)
    contradiction = contradiction.format(place=place, other_place=other_place,
                                          item=item, other_item=other_item)
    near = near.format(place=place, other_place=other_place,
                       item=item, other_item=other_item)
    canonical_chapter = 1 + index
    contradiction_chapter = min(chapter_total, canonical_chapter + chapter_total // 2)
    near_chapter = min(chapter_total, contradiction_chapter + chapter_total // 4 + 1)
    return {
        "id": f"c{index + 1:03d}",
        "entity": character["name"],
        "predicate": predicate,
        "canonical_chapter": canonical_chapter,
        "canonical_quote": f"{character['name']} {canonical}.",
        "contradiction_chapter": contradiction_chapter,
        "contradiction_quote": f"{character['name']} {contradiction}.",
        "near_chapter": near_chapter,
        "near_quote": f"{character['name']} {near}.",
        "near_reason": reason,
    }


def generate(chapters: int, words: int, seed: int, contradictions: int,
             near_misses: int, thread_count: int, resolved_count: int) -> dict:
    if chapters < 1 or words < 40:
        raise ValueError("chapters must be >= 1 and words >= 40")
    rng = random.Random(seed)
    entities = _entities()
    characters = entities["characters"]
    locations = entities["locations"]
    items = entities["items"]
    orgs = entities["organizations"]
    arcs = [
        {"index": index + 1,
         "name": (
             f"Arc {index + 1}: {PLACE_A[index % len(PLACE_A)]} "
             f"{PLACE_B[index % len(PLACE_B)]}"
         ),
         "start": 1, "end": chapters}
        for index in range(12)
    ]
    for index, arc in enumerate(arcs):
        arc["start"] = 1 + round(index * chapters / len(arcs))
        arc["end"] = round((index + 1) * chapters / len(arcs))
    thread_rows = []
    for index in range(thread_count):
        setup = 1 + (index * 13) % chapters
        payoff = min(chapters, setup + max(1, chapters // 8))
        thread_rows.append({
            "id": f"t{index + 1:03d}",
            "title": f"The {PLACE_A[index % len(PLACE_A)]} {ITEM_B[index % len(ITEM_B)]} thread",
            "setup_chapter": setup,
            "payoff_chapter": payoff if index < resolved_count else None,
            "state": "resolved" if index < resolved_count else "open",
            "summary": (
                f"A promise about the {ITEM_B[index % len(ITEM_B)]} that returns in "
                f"the {PLACE_B[index % len(PLACE_B)]}."
            ),
        })
    planted = []
    near = []
    for index in range(min(contradictions, chapters)):
        item = _contradiction_text(entities, 0, index, chapters)
        planted.append(item)
    for index in range(min(near_misses, chapters)):
        near.append({
            "id": f"n{index + 1:03d}",
            "entity": planted[index % len(planted)]["entity"] if planted else characters[index]["name"],
            "chapter": planted[index % len(planted)]["near_chapter"] if planted else 1,
            "quote": planted[index % len(planted)]["near_quote"] if planted else "",
            "reason": planted[index % len(planted)]["near_reason"] if planted else "near miss",
        })
    by_chapter = {}
    for item in planted:
        by_chapter.setdefault(item["canonical_chapter"], []).append(item["canonical_quote"])
        by_chapter.setdefault(item["contradiction_chapter"], []).append(item["contradiction_quote"])
        by_chapter.setdefault(item["near_chapter"], []).append(item["near_quote"])
    for thread in thread_rows:
        line = f"{thread['title']} returned to the story."
        by_chapter.setdefault(thread["setup_chapter"], []).append(line)
        if thread["payoff_chapter"]:
            by_chapter.setdefault(thread["payoff_chapter"], []).append(
                f"{thread['title']} was finally settled."
            )
    chapter_rows = []
    total_words = 0
    for number in range(1, chapters + 1):
        arc = next(arc for arc in arcs if arc["start"] <= number <= arc["end"])
        cast = [characters[(number * 7 + offset) % len(characters)] for offset in range(6)]
        loc = locations[(number * 3) % len(locations)]
        item = items[(number * 5) % len(items)]
        org = orgs[(number * 2) % len(orgs)]
        scene_target = max(30, words // 3)
        scenes = []
        for scene_index in range(3):
            paragraph = _paragraph(rng, cast[scene_index % len(cast)], loc, item, org, scene_target)
            if scene_index == 0 and number in by_chapter:
                paragraph = " ".join(by_chapter[number]) + " " + paragraph
            scenes.append(f"### Scene {scene_index + 1}\n\n{paragraph}")
        content = "\n\n***\n\n".join(scenes)
        word_count = len(content.split())
        total_words += word_count
        chapter_rows.append({
            "number": number,
            "title": f"Chapter {number}: {item['name']} at the {loc['name']}",
            "arc": arc["name"],
            "word_count": word_count,
            "content": content,
        })
    return {
        "seed": seed,
        "entities": entities,
        "arcs": arcs,
        "threads": thread_rows,
        "chapters": chapter_rows,
        "contradictions": planted,
        "near_misses": near,
        "totals": {"chapters": chapters, "words": total_words,
                   "characters": len(characters), "locations": len(locations),
                   "items": len(items), "organizations": len(orgs),
                   "threads": len(thread_rows), "contradictions": len(planted),
                   "near_misses": len(near)},
    }


def write_fixture(data: dict, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with (out / "chapters.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for chapter in data["chapters"]:
            handle.write(json.dumps(chapter, ensure_ascii=True, separators=(",", ":")))
            handle.write("\n")
    for name in ("entities", "arcs", "threads", "contradictions", "near_misses"):
        payload = data[name]
        (out / f"{name}.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8"
        )
    manifest = {
        "generator": "scripts/generate_fixture.py",
        "seed": data["seed"],
        "totals": data["totals"],
        "files": {
            "chapters": "chapters.jsonl",
            "entities": "entities.json",
            "arcs": "arcs.json",
            "threads": "threads.json",
            "contradictions": "contradictions.json",
            "near_misses": "near_misses.json",
        },
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True), encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a synthetic scale fixture")
    parser.add_argument("--chapters", type=int, default=1100)
    parser.add_argument("--words", type=int, default=900)
    parser.add_argument("--seed", type=int, default=20261125)
    parser.add_argument("--contradictions", type=int, default=100)
    parser.add_argument("--near-misses", type=int, default=100)
    parser.add_argument("--threads", type=int, default=70)
    parser.add_argument("--resolved-threads", type=int, default=30)
    parser.add_argument("--out", type=Path, default=Path("data/scale-fixture"))
    args = parser.parse_args()
    data = generate(args.chapters, args.words, args.seed, args.contradictions,
                    args.near_misses, args.threads, args.resolved_threads)
    write_fixture(data, args.out)
    totals = data["totals"]
    print(json.dumps({"out": str(args.out), **totals}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())