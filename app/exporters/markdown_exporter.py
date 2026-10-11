"""Markdown exporter — outputs the complete book as a single .md file."""

from __future__ import annotations

from pathlib import Path

from ..models.book_project import BookProject, EBOOK_TYPE_LABELS


class MarkdownExporter:
    """Export a BookProject to a Markdown file."""

    @staticmethod
    def export(project: BookProject, file_path: str) -> None:
        """Write the full book as a single Markdown document."""
        lines: list[str] = []

        meta = project.metadata
        type_label = EBOOK_TYPE_LABELS.get(project.ebook_type, "Book")

        # --- Front matter ---
        if project.frontmatter:
            lines.append(project.frontmatter.strip())
            lines.append("")
            lines.append("---")
            lines.append("")

        # --- Title page ---
        lines.append(f"# {meta.title}")
        if meta.subtitle:
            lines.append(f"## {meta.subtitle}")
        lines.append("")
        lines.append(f"**by {meta.author}**")
        if meta.co_authors:
            lines.append(f"*with {meta.co_authors}*")
        lines.append("")
        if meta.description:
            lines.append(f"> {meta.description}")
            lines.append("")

        # --- Table of contents ---
        if project.generation_config.include_toc and project.chapters:
            lines.append("## Table of Contents")
            lines.append("")
            for ch in project.chapters:
                status = " *(generated)*" if ch.content_generated else ""
                lines.append(f"- {ch.index + 1}. {ch.title}{status}")
            lines.append("")

        # --- Chapters ---
        for ch in project.chapters:
            lines.append(f"---")
            lines.append("")
            lines.append(f"## Chapter {ch.index + 1}: {ch.title}")
            lines.append("")
            if ch.synopsis:
                lines.append(f"*{ch.synopsis}*")
                lines.append("")
            if ch.content_markdown:
                lines.append(ch.content_markdown.strip())
            else:
                lines.append("*[Chapter not yet generated]*")
            lines.append("")

        # --- Back matter ---
        if project.backmatter:
            lines.append("---")
            lines.append("")
            lines.append(project.backmatter.strip())
            lines.append("")

        # --- Write file ---
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = "\n".join(lines)
        path.write_text(content, encoding="utf-8")