"""Manuscript and wiki export.

DOCX, EPUB, and PDF use Pandoc. DOCX gets a generated reference document with
double-spaced 12 pt Georgia, indented paragraphs, and a page-number footer; EPUB
gets the same typography as CSS; PDF is printed from Pandoc HTML with a serif
print stylesheet. Missing optional tools return 503 with an install hint rather
than a half-written file.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.story_models import Story
from app.schemas.backup import StoryBackup
from app.services.backup import build_backup

ExportFormat = Literal["markdown", "docx", "epub", "pdf"]
MEDIA_TYPES = {
    "markdown": "text/markdown; charset=utf-8",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "epub": "application/epub+zip",
    "pdf": "application/pdf",
}
EXTENSIONS = {"markdown": "md", "docx": "docx", "epub": "epub", "pdf": "pdf"}

EPUB_CSS = """
body { font-family: Georgia, 'Times New Roman', serif; font-size: 12pt; line-height: 2; margin: 0 5%; }
p { margin: 0; text-indent: 1.5em; }
h1, h2 { font-family: Georgia, 'Times New Roman', serif; font-weight: normal; text-align: center; }
h2 { page-break-before: always; margin: 2em 0 1.5em; font-size: 1.5em; }
blockquote { margin: 1em 2em; font-style: italic; }
"""

PDF_CSS = """
@page {
  size: letter;
  margin: 1in;
  @bottom-center { content: counter(page); font-family: Georgia, 'Times New Roman', serif; font-size: 9pt; color: #6f6c63; }
}
html { font-size: 12pt; }
body { margin: 0; color: #181713; background: #fff; font-family: Georgia, 'Times New Roman', serif; font-size: 12pt; line-height: 2; }
p { margin: 0; text-indent: 1.5em; orphans: 2; widows: 2; }
h1, h2 { break-before: page; margin: 0 0 1.5em; font-family: Georgia, 'Times New Roman', serif; font-size: 20pt; font-weight: normal; line-height: 1.3; text-align: center; }
h3 { margin: 1.4em 0 .4em; font-family: Georgia, 'Times New Roman', serif; font-size: 14pt; font-weight: bold; }
blockquote { margin: 1em 2em; font-style: italic; }
.title-page { display: flex; height: 8.4in; align-items: center; justify-content: center; break-after: page; text-align: center; }
.title-page h1 { break-before: auto; margin: 0; font-size: 30pt; line-height: 1.25; }
.title-page p { margin-top: 1.5em; color: #6f6c63; font-size: 11pt; text-indent: 0; }
"""


def _executable(*candidates: str | Path | None) -> str | None:
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    return shutil.which("pandoc")


def pandoc_binary() -> str | None:
    return _executable(
        shutil.which("pandoc"),
        Path.home() / "AppData" / "Local" / "Pandoc" / "pandoc.exe",
        Path("C:/Program Files/Pandoc/pandoc.exe"),
    )


def browser_binary() -> str | None:
    return _executable(
        Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
        Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
        Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
        shutil.which("google-chrome"),
        shutil.which("chromium"),
    )


def slug_filename(title: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in " -_" else "-" for char in title).strip(" -")
    return cleaned[:80] or "manuscript"


def _render_markdown(backup: StoryBackup, include_wiki: bool) -> str:
    parts = [f"# {backup.story.title}", ""]
    for chapter in sorted(backup.chapters, key=lambda row: (row.position, row.chapter_number)):
        parts.extend(
            [
                f"## Chapter {chapter.chapter_number}: {chapter.title}",
                "",
                chapter.content.strip(),
                "",
            ]
        )
    if include_wiki:
        parts.extend(_wiki_appendix(backup))
    return _scene_glyphs("\n".join(parts).strip()) + "\n"


def _wiki_appendix(backup: StoryBackup) -> list[str]:
    parts = ["# Appendix: Story wiki", ""]
    if backup.arcs:
        parts.extend(["## Arcs", ""])
        for arc in backup.arcs:
            parts.append(f"### {arc.name}")
            if arc.summary:
                parts.extend(["", arc.summary.strip()])
            parts.append("")
    active = [entity for entity in backup.entities if entity.status != "merged"]
    if active:
        parts.extend(["## Entities", ""])
        for entity in active:
            parts.extend([f"### {entity.name}", "", f"*{entity.entity_type.replace('_', ' ')}*", ""])
            if entity.summary:
                parts.extend([entity.summary.strip(), ""])
            aliases = [alias.alias for alias in entity.aliases if alias.alias != entity.name]
            if aliases:
                parts.extend(["Also known as: " + ", ".join(aliases), ""])
            accepted = [fact for fact in entity.facts if fact.status == "accepted"]
            for fact in accepted:
                value = fact.value_text or (str(fact.value_number) if fact.value_number is not None else "")
                if value:
                    parts.append(f"- **{fact.predicate}**: {value}")
            if accepted:
                parts.append("")
    if backup.threads:
        parts.extend(["## Threads", ""])
        for thread in backup.threads:
            parts.append(f"### {thread.title}")
            parts.extend(["", f"*{thread.state.replace('_', ' ')}*", ""])
            if thread.description:
                parts.extend([thread.description.strip(), ""])
            if thread.setup_quote:
                parts.extend([f"> {thread.setup_quote}", ""])
    return parts


def _scene_glyphs(text: str) -> str:
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and set(stripped) <= {"*", "-", " "} and stripped.count("*") + stripped.count("-") >= 3:
            lines.append("⁂")
        else:
            lines.append(line)
    return "\n".join(lines)


def _pandoc(markdown: str, output: Path, args: list[str]) -> None:
    binary = pandoc_binary()
    if not binary:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pandoc is required for DOCX, EPUB, and PDF export. Install it from https://pandoc.org/installing.html.",
        )
    with tempfile.TemporaryDirectory(prefix="stillroom-export-") as folder:
        source = Path(folder) / "manuscript.md"
        source.write_text(markdown, encoding="utf-8")
        command = [binary, str(source), "-o", str(output), *args]
        result = subprocess.run(command, capture_output=True, text=True, timeout=180, check=False)
    if result.returncode != 0 or not output.exists():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Document conversion failed: {result.stderr.strip()[:400] or 'pandoc exited without output'}",
        )


def _reference_docx(path: Path) -> None:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Inches, Pt

    document = Document()
    section = document.sections[0]
    section.left_margin = section.right_margin = Inches(1)
    section.top_margin = section.bottom_margin = Inches(1)

    normal: Any = document.styles["Normal"]
    normal.font.name = "Georgia"
    normal.font.size = Pt(12)
    normal.paragraph_format.line_spacing = 2.0
    normal.paragraph_format.first_line_indent = Inches(0.5)
    normal.paragraph_format.space_after = Pt(0)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), "Georgia")

    title: Any = document.styles["Title"]
    title.font.name = "Georgia"
    title.font.size = Pt(28)
    title.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.first_line_indent = Inches(0)
    title.paragraph_format.space_before = Pt(180)

    for name, size, page_break in (("Heading 1", 20, True), ("Heading 2", 18, True), ("Heading 3", 14, False)):
        style: Any = document.styles[name]
        style.font.name = "Georgia"
        style.font.size = Pt(size)
        style.font.bold = name == "Heading 3"
        style.paragraph_format.first_line_indent = Inches(0)
        style.paragraph_format.space_before = Pt(0)
        style.paragraph_format.space_after = Pt(18)
        style.paragraph_format.line_spacing = 2.0
        style.paragraph_format.page_break_before = page_break
        style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER if page_break else WD_ALIGN_PARAGRAPH.LEFT

    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.paragraph_format.first_line_indent = Inches(0)
    run = footer.add_run()
    run.font.name = "Georgia"
    run.font.size = Pt(10)
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instruction = OxmlElement("w:instrText")
    instruction.set(qn("xml:space"), "preserve")
    instruction.text = " PAGE "
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(begin)
    run._r.append(instruction)
    run._r.append(end)
    document.save(str(path))


def _docx(backup: StoryBackup, include_wiki: bool, output: Path) -> None:
    markdown = _render_markdown(backup, include_wiki)
    markdown = markdown.replace(f"# {backup.story.title}\n", "", 1)
    markdown = _scene_glyphs(markdown)
    with tempfile.TemporaryDirectory(prefix="stillroom-reference-") as folder:
        reference = Path(folder) / "reference.docx"
        _reference_docx(reference)
        _pandoc(
            markdown,
            output,
            [
                "--from",
                "markdown+raw_attribute",
                "--to",
                "docx",
                "--reference-doc",
                str(reference),
                "--metadata",
                f"title={backup.story.title}",
            ],
        )


def _epub(backup: StoryBackup, include_wiki: bool, output: Path) -> None:
    markdown = _render_markdown(backup, include_wiki).replace(f"# {backup.story.title}\n", "", 1)
    markdown = _scene_glyphs(markdown)
    with tempfile.TemporaryDirectory(prefix="stillroom-epub-") as folder:
        css = Path(folder) / "stillroom.css"
        css.write_text(EPUB_CSS, encoding="utf-8")
        _pandoc(
            markdown,
            output,
            [
                "--from",
                "markdown+raw_attribute",
                "--to",
                "epub3",
                "--toc",
                "--toc-depth=2",
                "--split-level=2",
                "--css",
                str(css),
                "--metadata",
                f"title={backup.story.title}",
                "--metadata",
                "lang=en",
            ],
        )


def _pdf(backup: StoryBackup, include_wiki: bool, output: Path) -> None:
    browser = browser_binary()
    if not browser:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chrome or Edge is required to print PDF export.",
        )
    markdown = _render_markdown(backup, include_wiki).replace(f"# {backup.story.title}\n", "", 1)
    markdown = _scene_glyphs(markdown)
    with tempfile.TemporaryDirectory(prefix="stillroom-pdf-") as folder:
        html_fragment = Path(folder) / "body.html"
        _pandoc(
            markdown,
            html_fragment,
            ["--from", "markdown+raw_attribute", "--to", "html5"],
        )
        body = html_fragment.read_text(encoding="utf-8")
        title = backup.story.title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        html = (
            "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>"
            + title
            + "</title><style>"
            + PDF_CSS
            + "</style></head><body><section class=\"title-page\"><div><h1>"
            + title
            + "</h1><p>Exported "
            + datetime.now(UTC).strftime("%B %d, %Y")
            + "</p></div></section>"
            + body
            + "</body></html>"
        )
        page = Path(folder) / "manuscript.html"
        page.write_text(html, encoding="utf-8")
        profile = Path(folder) / "profile"
        command = [
            browser,
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            "--no-pdf-header-footer",
            f"--user-data-dir={profile}",
            f"--print-to-pdf={output}",
            page.as_uri(),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=180, check=False)
        if result.returncode != 0 or not output.exists():
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"PDF rendering failed: {result.stderr.strip()[:400] or 'browser exited without output'}",
            )


async def render_export(
    session: AsyncSession, story: Story, fmt: ExportFormat, include_wiki: bool
) -> tuple[bytes, str, str]:
    backup = await build_backup(session, story)
    if fmt == "markdown":
        body = _render_markdown(backup, include_wiki).encode("utf-8")
    else:
        with tempfile.TemporaryDirectory(prefix="stillroom-export-") as folder:
            output = Path(folder) / f"manuscript.{EXTENSIONS[fmt]}"
            if fmt == "docx":
                _docx(backup, include_wiki, output)
            elif fmt == "epub":
                _epub(backup, include_wiki, output)
            else:
                _pdf(backup, include_wiki, output)
            body = output.read_bytes()
    filename = f"{slug_filename(backup.story.title)}.{EXTENSIONS[fmt]}"
    return body, MEDIA_TYPES[fmt], filename