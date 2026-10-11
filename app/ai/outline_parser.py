"""Outline parser — extracts chapter titles and synopses from generated outlines.

Supports various LLM output formats:
- "Chapter 1: Title" or "1. Title" or "Chapter 1 - Title"
- Bullet points or numbered lists under each chapter heading
- Key themes/characters mentioned per chapter
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParsedChapter:
    """A chapter extracted from an outline."""
    index: int
    title: str
    synopsis: str = ""
    themes: list[str] = None
    characters: list[str] = None

    def __post_init__(self):
        if self.themes is None:
            self.themes = []
        if self.characters is None:
            self.characters = []


def parse_outline_to_chapters(outline_text: str) -> list[ParsedChapter]:
    """Parse a generated outline into structured chapter data.

    Handles multiple common formats:
    - "Chapter N: Title" / "Chapter N - Title" / "1. Title"
    - Content below each heading (synopsis, key points, themes)
    - Bullet lists (- item, * item, • item)
    - Numbered sub-lists

    Returns a list of ParsedChapter in order.
    """
    if not outline_text.strip():
        return []

    lines = outline_text.split("\n")
    chapters: list[ParsedChapter] = []
    current_chapter: Optional[ParsedChapter] = None
    current_content_lines: list[str] = []

    # Regex patterns for chapter headings
    chapter_patterns = [
        # "Chapter 1: The Beginning" or "Chapter 1:  The Beginning"
        re.compile(r"^(?:Chapter\s+)?(\d+)[\s:.\-—]+(.+)$", re.IGNORECASE),
        # "1. The Beginning" or "1) The Beginning"
        re.compile(r"^(\d+)[.)\s]+(.+)$"),
    ]

    def _is_chapter_heading(line: str) -> Optional[tuple[int, str]]:
        stripped = line.strip()
        if not stripped:
            return None
        for pattern in chapter_patterns:
            m = pattern.match(stripped)
            if m:
                num = int(m.group(1))
                title = m.group(2).strip().rstrip(":")
                # Filter out obviously non-chapter lines
                if len(title) < 2:
                    continue
                # Skip if title looks like a sentence (too long, no capitalization pattern)
                return (num, title)
        return None

    def _is_list_item(line: str) -> bool:
        stripped = line.strip()
        return bool(re.match(r"^[\s]*[-*•]\s+", stripped) or bool(
            re.match(r"^[\s]*\d+[.)]\s+", stripped)
        )

    def _finalize_chapter():
        nonlocal current_chapter, current_content_lines
        if current_chapter is not None:
            content = "\n".join(current_content_lines).strip()
            # Extract synopsis (first non-list, non-empty paragraph)
            synopsis_parts = []
            for cline in content.split("\n"):
                cline = cline.strip()
                if not cline:
                    continue
                # Skip list markers
                if _is_list_item(cline):
                    # Extract list item content (remove marker)
                    cleaned = re.sub(r"^[\s]*[-*•]\s+", "", cline)
                    cleaned = re.sub(r"^[\s]*\d+[.)]\s+", "", cleaned)
                    synopsis_parts.append(cleaned)
                    continue
                # Skip "key" labels
                if re.match(r"^(Key|Characters?|Themes?|Concepts?|Setting|Plot|Conflict|Resolution|Arc)\s*:", cline, re.IGNORECASE):
                    continue
                synopsis_parts.append(cline)
            current_chapter.synopsis = " ".join(synopsis_parts[:5])  # Keep first 5 meaningful lines

            # Extract themes/characters from list items
            for cline in content.split("\n"):
                cline = cline.strip()
                if not cline:
                    continue
                cleaned = re.sub(r"^[\s]*[-*•]\s+", "", cline)
                cleaned = re.sub(r"^[\s]*\d+[.)]\s+", "", cleaned)
                cleaned_lower = cleaned.lower()
                if any(kw in cleaned_lower for kw in ("character", "introduc", "appear", "protagonist", "antagonist")):
                    # Extract names from the line
                    names = re.findall(r'"([^"]+)"', cleaned) or re.findall(r"'([^']+)'", cleaned)
                    if names:
                        current_chapter.characters.extend(names)
                    else:
                        # Try to extract a name (capitalized words)
                        words = cleaned.split()
                        for w in words:
                            if w[0].isupper() and len(w) > 2 and w.lower() not in (
                                "the", "and", "but", "for", "with", "from", "that", "this"
                            ):
                                current_chapter.characters.append(w)
                                break

            chapters.append(current_chapter)
            current_chapter = None
            current_content_lines = []

    for line in lines:
        heading = _is_chapter_heading(line)
        if heading:
            _finalize_chapter()
            num, title = heading
            current_chapter = ParsedChapter(index=num - 1, title=title)
            current_content_lines = []
        elif current_chapter is not None:
            current_content_lines.append(line)

    _finalize_chapter()

    # Re-index sequentially
    for i, ch in enumerate(chapters):
        ch.index = i

    return chapters


def apply_parsed_chapters_to_project(
    project, parsed: list[ParsedChapter]
) -> int:
    """Apply parsed outline chapters to a BookProject.

    - Clears existing chapters
    - Creates new chapters with titles and synopses from the outline
    - Returns the number of chapters created
    """
    project.chapters.clear()

    for pc in parsed:
        ch = project.add_chapter(title=pc.title, synopsis=pc.synopsis)

    project.generation_config.total_chapters = len(project.chapters)
    return len(project.chapters)