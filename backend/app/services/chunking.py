"""Sentence-aware scene chunking for retrieval v2.

The old splitter cut on headings and blank lines and capped at 2,800
characters without overlap. This one finds scenes first, then fills 300-600
token chunks on sentence boundaries with a small overlap. Line ranges always
point back to the exact prose, and the hash lets the indexer reuse embeddings
when a chapter did not really change.

Token counts are approximate (words x 1.3); an exact tokenizer is a Phase 6
concern and is not worth a model dependency in the request path.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

TARGET_TOKENS_MIN = 300
TARGET_TOKENS_MAX = 600
# Four characters per token is the usual English approximation; the exact count
# is stored per chunk once text is available.
TARGET_CHARS_MIN = 1200
TARGET_CHARS_MAX = 2400
OVERLAP_FRACTION = 0.12

HEADING_RE = re.compile(
    r"^(?:#{1,3}\s+\S.*|(?:INT\.|EXT\.|INT/EXT\.)\s+.*|CHAPTER\s+[\wIVXLC]+.*)$",
    re.IGNORECASE,
)
SEPARATOR_RE = re.compile(r"^\s*(?:(?:\*\s*){3,}|-{3,}|_{3,})\s*$")
SENTENCE_END_RE = re.compile(r"[.!?]+[\"'”’)\]]*(?=\s|$)")
ABBREVIATIONS = {"mr.", "mrs.", "ms.", "dr.", "st.", "vs.", "etc.", "jr.", "sr."}


@dataclass(frozen=True)
class Scene:
    start_line: int
    end_line: int
    text: str


@dataclass(frozen=True)
class Chunk:
    text: str
    start_line: int
    end_line: int
    scene_index: int
    chunk_index: int
    token_count: int
    content_hash: str


def _has_text(lines: list[str], start_line: int, end_line: int) -> bool:
    return any(line.strip() for line in lines[start_line - 1 : end_line])


def detect_scenes(content: str) -> list[Scene]:
    """Split a chapter into scenes by headings, separators, then paragraphs."""
    lines = content.splitlines()
    if not lines:
        return []

    boundaries: list[tuple[int, int]] = []
    explicit = False
    current_start = 1
    blank_run = 0

    def close(end_line: int) -> None:
        nonlocal current_start
        if end_line >= current_start and _has_text(lines, current_start, end_line):
            boundaries.append((current_start, end_line))
        current_start = end_line + 1

    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if HEADING_RE.match(stripped):
            if line_number > current_start:
                close(line_number - 1)
            current_start = line_number
            explicit = True
            blank_run = 0
            continue
        if SEPARATOR_RE.match(stripped):
            if line_number > current_start:
                close(line_number - 1)
            current_start = line_number + 1
            explicit = True
            blank_run = 0
            continue
        if not stripped:
            blank_run += 1
            if blank_run >= 2:
                close(line_number - blank_run)
                current_start = line_number + 1
                explicit = True
            continue
        blank_run = 0
    close(len(lines))

    if explicit and boundaries:
        return [
            Scene(start_line=start, end_line=end, text="\n".join(lines[start - 1 : end]))
            for start, end in boundaries
        ]

    # No headings, separators, or double blank lines: group paragraphs into
    # scene-sized blocks instead of treating every paragraph as its own scene.
    paragraphs: list[tuple[int, int]] = []
    start = None
    for line_number, line in enumerate(lines, start=1):
        if line.strip():
            start = line_number if start is None else start
        elif start is not None:
            paragraphs.append((start, line_number - 1))
            start = None
    if start is not None:
        paragraphs.append((start, len(lines)))
    if not paragraphs:
        return []

    scenes: list[Scene] = []
    group_start, group_end = paragraphs[0]
    group_chars = len("\n".join(lines[group_start - 1 : group_end]))
    for paragraph_start, paragraph_end in paragraphs[1:]:
        paragraph_chars = len("\n".join(lines[paragraph_start - 1 : paragraph_end]))
        if group_chars + paragraph_chars <= TARGET_CHARS_MAX:
            group_end = paragraph_end
            group_chars += paragraph_chars
            continue
        scenes.append(
            Scene(
                start_line=group_start,
                end_line=group_end,
                text="\n".join(lines[group_start - 1 : group_end]),
            )
        )
        group_start, group_end, group_chars = paragraph_start, paragraph_end, paragraph_chars
    scenes.append(
        Scene(
            start_line=group_start,
            end_line=group_end,
            text="\n".join(lines[group_start - 1 : group_end]),
        )
    )
    return scenes


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    """Character spans for sentence-sized units, never cutting mid-sentence."""
    spans: list[tuple[int, int]] = []
    start = 0
    for match in SENTENCE_END_RE.finditer(text):
        end = match.end()
        word_start = max(0, match.start() - 4)
        word = text[word_start : match.end()].casefold()
        if word in ABBREVIATIONS:
            continue
        previous = text[match.start() - 1 : match.start()]
        if previous.isalpha() and text[match.start() - 2 : match.start()].isupper():
            # Initials such as "J." should not end a sentence.
            continue
        while end < len(text) and text[end].isspace():
            end += 1
        if end > start:
            spans.append((start, end))
            start = end
    if start < len(text):
        spans.append((start, len(text)))
    return spans or ([] if not text.strip() else [(0, len(text))])


def approximate_tokens(text: str) -> int:
    return max(1, round(len(text.split()) * 1.3))


def content_hash(text: str) -> str:
    normalized = " ".join(text.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _scene_chunks(scene: Scene, scene_index: int) -> list[Chunk]:
    spans = _sentence_spans(scene.text)
    if not spans:
        return []
    overlap_chars = round(TARGET_CHARS_MAX * OVERLAP_FRACTION)
    chunks: list[Chunk] = []
    index = 0
    chunk_index = 0
    while index < len(spans):
        start_index = index
        chars = 0
        while index < len(spans):
            sentence_chars = spans[index][1] - spans[index][0]
            if chars and chars + sentence_chars > TARGET_CHARS_MAX:
                break
            chars += sentence_chars
            index += 1
            if chars >= TARGET_CHARS_MIN:
                break
        chunk_start = spans[start_index][0]
        chunk_end = spans[index - 1][1]
        raw = scene.text[chunk_start:chunk_end]
        left_trim = len(raw) - len(raw.lstrip())
        right_trim = len(raw.rstrip())
        start_offset = chunk_start + left_trim
        end_offset = chunk_start + right_trim
        text = scene.text[start_offset:end_offset]
        if text:
            start_line = scene.start_line + scene.text[:start_offset].count("\n")
            end_line = scene.start_line + scene.text[: max(end_offset - 1, start_offset)].count("\n")
            chunks.append(
                Chunk(
                    text=text,
                    start_line=start_line,
                    end_line=end_line,
                    scene_index=scene_index,
                    chunk_index=chunk_index,
                    token_count=approximate_tokens(text),
                    content_hash=content_hash(text),
                )
            )
            chunk_index += 1
        if index >= len(spans):
            break
        # Carry the tail of the previous chunk into the next one. Never step
        # back onto the chunk start, or the loop would not advance.
        overlap_index = index - 1
        overlap = spans[overlap_index][1] - spans[overlap_index][0]
        while overlap_index - 1 > start_index and overlap < overlap_chars:
            overlap_index -= 1
            overlap += spans[overlap_index][1] - spans[overlap_index][0]
        index = overlap_index if overlap_index > start_index else index
    return chunks


def chunk_chapter(content: str) -> list[Chunk]:
    """Chunk one chapter, preserving scene order and exact line ranges."""
    chunks: list[Chunk] = []
    for scene_index, scene in enumerate(detect_scenes(content)):
        for chunk in _scene_chunks(scene, scene_index):
            chunks.append(
                Chunk(
                    text=chunk.text,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    scene_index=chunk.scene_index,
                    chunk_index=len(chunks),
                    token_count=chunk.token_count,
                    content_hash=chunk.content_hash,
                )
            )
    return chunks
