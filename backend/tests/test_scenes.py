from app.services.indexing import split_into_scenes


def test_blank_line_splits_a_long_scene_but_not_a_short_one():
    long_first = "word " * 400
    scenes = split_into_scenes(f"{long_first}\n\nsecond block")
    assert len(scenes) == 2
    assert scenes[1].text == "second block"

    short = split_into_scenes("first block\n\nsecond block")
    assert len(short) == 1
    assert "second block" in short[0].text


def test_scene_headings_start_a_new_scene():
    content = "Intro paragraph.\nINT. NIGHT WATCH HQ - NIGHT\nThe captain waits.\n"
    scenes = split_into_scenes(content)
    assert [scene.text.splitlines()[0] for scene in scenes] == [
        "Intro paragraph.",
        "INT. NIGHT WATCH HQ - NIGHT",
    ]


def test_long_scene_is_cut_near_the_character_limit():
    content = "\n".join(f"line {number} " + ("x" * 100) for number in range(60))
    scenes = split_into_scenes(content, max_characters=800)
    assert len(scenes) > 1
    for scene in scenes:
        # A single appended line can push a scene past the cap, but not by much.
        assert len(scene.text) < 800 + 120


def test_line_numbers_map_back_to_the_original_text():
    content = "\n".join(["first", "second", "INT. ROOM", "third", "fourth"])
    scenes = split_into_scenes(content)
    lines = content.splitlines()
    for scene in scenes:
        assert lines[scene.start_line - 1] == scene.text.splitlines()[0]
        assert lines[scene.end_line - 1] == scene.text.splitlines()[-1]


def test_empty_content_produces_no_scenes():
    assert split_into_scenes("") == []
    assert split_into_scenes("\n\n   \n") == []
