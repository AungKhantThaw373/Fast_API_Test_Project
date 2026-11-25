"""Chunking v2: scenes, sentence boundaries, overlap, and exact line ranges."""

from app.services.chunking import chunk_chapter, detect_scenes


def test_separator_lines_split_scenes():
    content = "Mira crossed the yard.\n\n***\n\nThe gate was locked.\n\n---\n\nKael waited."
    scenes = detect_scenes(content)
    assert len(scenes) == 3
    assert "Mira crossed" in scenes[0].text
    assert "gate was locked" in scenes[1].text
    assert "Kael waited" in scenes[2].text


def test_headings_start_scenes():
    content = "Chapter One\n\nMira crossed the yard.\n\n# The Gate\n\nThe gate was locked."
    scenes = detect_scenes(content)
    assert len(scenes) == 2
    assert scenes[0].text.startswith("Chapter One")
    assert "The Gate" in scenes[1].text


def test_long_scene_splits_on_sentence_boundaries_with_overlap():
    sentences = [
        f"Sentence {index} carries a little more detail so the chunk reaches its target size."
        for index in range(90)
    ]
    content = "\n\n".join([" ".join(sentences[:45]), " ".join(sentences[45:])])
    chunks = chunk_chapter(content)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert chunk.text.endswith(".")
        assert not chunk.text.endswith(" det")
        assert 1 <= chunk.token_count <= 900
    # At least one sentence must be carried into the following chunk.
    assert any(chunks[0].text[-80:] in chunk.text for chunk in chunks[1:])


def test_line_ranges_map_back_to_the_original_text():
    lines = [
        "Mira crossed the yard with the brass compass in her fist.",
        "",
        "***",
        "",
        "The gate was locked, and Kael waited beside it with a lantern.",
        "",
        "She did not speak until the bell rang.",
    ]
    content = "\n".join(lines)
    chunks = chunk_chapter(content)
    assert chunks
    for chunk in chunks:
        original = "\n".join(lines[chunk.start_line - 1 : chunk.end_line])
        assert chunk.text in original


def test_a_chapter_without_scene_breaks_still_chunks():
    paragraphs = [
        f"Paragraph {index} has two sentences. The second one adds a little atmosphere to the scene."
        for index in range(40)
    ]
    chunks = chunk_chapter("\n\n".join(paragraphs))
    assert len(chunks) >= 2
    assert chunks[0].start_line == 1
    assert chunks[-1].end_line == len(paragraphs) * 2 - 1


def test_a_short_scene_is_one_chunk():
    chunks = chunk_chapter("Mira crossed the yard.\n\n***\n\nThe gate was locked.")
    assert len(chunks) == 2
    assert chunks[0].scene_index == 0
    assert chunks[1].scene_index == 1
    assert chunks[0].content_hash != chunks[1].content_hash


def test_abbreviations_do_not_end_sentences():
    chunks = chunk_chapter("Mr. Voss met Dr. Hale at the gate. They said nothing.")
    assert len(chunks) == 1
    assert "Mr. Voss met Dr. Hale" in chunks[0].text


def test_empty_content_has_no_chunks():
    assert chunk_chapter("") == []
