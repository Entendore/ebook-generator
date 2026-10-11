"""PDF exporter — outputs the complete book as a professional .pdf file.

Uses the `reportlab` library to create a polished PDF with:
- Title page (centered title, author, date)
- Auto-generated table of contents
- Front matter (rendered from markdown)
- Chapters (each on a new page)
- Back matter (if present)
- Page numbers in footer and 1-inch margins
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from ..models.book_project import BookProject, EBOOK_TYPE_LABELS


def _strip_md(md: str) -> str:
    """Convert basic Markdown to plain text.

    - Strips # header markers but keeps the text
    - Strips **bold** and *italic* markers
    - Strips ``` code fences
    - Converts --- to a blank line
    """
    if not md:
        return ""

    lines = md.split("\n")
    result: list[str] = []
    in_code_block = False

    for line in lines:
        stripped = line.strip()

        # Toggle code fence
        if stripped.startswith("```"):
            if in_code_block:
                in_code_block = False
                result.append("")  # blank line after code block
            else:
                in_code_block = True
            continue

        if in_code_block:
            result.append(line)
            continue

        # Horizontal rule → blank line
        if stripped in ("---", "***", "___"):
            result.append("")
            continue

        # Strip header markers (# ## ### etc.) but keep the text
        header_match = re.match(r"^(#{1,6})\s+", stripped)
        if header_match:
            stripped = stripped[header_match.end():]

        # Strip bold markers
        stripped = re.sub(r"\*\*(.+?)\*\*", r"\1", stripped)

        # Strip italic markers
        stripped = re.sub(r"\*(.+?)\*", r"\1", stripped)

        # Strip inline code backticks
        stripped = re.sub(r"`(.+?)`", r"\1", stripped)

        result.append(stripped)

    return "\n".join(result)


class PDFExporter:
    """Export a BookProject to a professional PDF file using ReportLab."""

    @staticmethod
    def export(project: BookProject, file_path: str) -> None:
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib.units import inch
            from reportlab.platypus import (
                SimpleDocTemplate,
                Paragraph,
                Spacer,
                PageBreak,
            )
        except ImportError:
            raise ImportError(
                "reportlab is not installed. Install it with: pip install reportlab"
            )

        meta = project.metadata

        # --- Ensure output directory exists ---
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)

        # --- Build styles ---
        base_styles = getSampleStyleSheet()

        book_title_style = base_styles["Title"]
        book_title_style.fontSize = 24
        book_title_style.fontName = "Helvetica-Bold"
        book_title_style.spaceAfter = 12
        book_title_style.alignment = 1  # center

        book_author_style = base_styles["Normal"]
        book_author_style.fontSize = 14
        book_author_style.fontName = "Helvetica"
        book_author_style.spaceAfter = 6
        book_author_style.alignment = 1  # center

        chapter_title_style = base_styles["Heading1"]
        chapter_title_style.fontSize = 18
        chapter_title_style.fontName = "Helvetica-Bold"
        chapter_title_style.spaceBefore = 20
        chapter_title_style.spaceAfter = 12

        body_style = base_styles["Normal"]
        body_style.fontSize = 11
        body_style.fontName = "Times-Roman"
        body_style.leading = 16
        body_style.firstLineIndent = 24
        body_style.spaceAfter = 6

        toc_title_style = base_styles["Heading1"]
        toc_title_style.fontSize = 18
        toc_title_style.fontName = "Helvetica-Bold"
        toc_title_style.spaceAfter = 18

        toc_entry_style = base_styles["Normal"]
        toc_entry_style.fontSize = 12
        toc_entry_style.fontName = "Times-Roman"
        toc_entry_style.leading = 20
        toc_entry_style.leftIndent = 36

        # --- Footer callback for page numbers ---
        def _add_page_number(canvas, doc):
            """Draw page number at bottom center."""
            page_num = canvas.getPageNumber()
            text = f"- {page_num} -"
            canvas.saveState()
            canvas.setFont("Times-Roman", 9)
            canvas.drawCentredString(letter[0] / 2, 0.5 * inch, text)
            canvas.restoreState()

        # --- Build the story (list of flowables) ---
        story: list = []

        # ---- 1. Title page ----
        story.append(Spacer(1, 2.5 * inch))
        story.append(Paragraph(meta.title, book_title_style))
        if meta.subtitle:
            story.append(Spacer(1, 12))
            subtitle_style = base_styles["Normal"]
            subtitle_style.fontSize = 16
            subtitle_style.fontName = "Helvetica-Oblique"
            subtitle_style.alignment = 1
            story.append(Paragraph(meta.subtitle, subtitle_style))
        story.append(Spacer(1, 24))
        story.append(Paragraph(f"by {meta.author}", book_author_style))
        if meta.co_authors:
            story.append(Spacer(1, 6))
            story.append(Paragraph(f"with {meta.co_authors}", book_author_style))
        story.append(Spacer(1, 36))
        date_style = base_styles["Normal"]
        date_style.fontSize = 11
        date_style.fontName = "Times-Italic"
        date_style.alignment = 1
        story.append(Paragraph(datetime.now().strftime("%B %d, %Y"), date_style))
        story.append(PageBreak())

        # ---- 2. Table of contents ----
        story.append(Paragraph("Table of Contents", toc_title_style))
        story.append(Spacer(1, 12))
        for ch in project.chapters:
            ch_num = ch.index + 1
            entry_text = f"Chapter {ch_num}: {ch.title}"
            story.append(Paragraph(entry_text, toc_entry_style))
        story.append(PageBreak())

        # ---- 3. Front matter ----
        if project.frontmatter:
            story.append(Paragraph("Front Matter", chapter_title_style))
            story.append(Spacer(1, 12))
            frontmatter_text = _strip_md(project.frontmatter)
            for para in frontmatter_text.split("\n\n"):
                para = para.strip()
                if not para:
                    continue
                # Collapse single newlines into spaces within a paragraph
                para = para.replace("\n", " ")
                story.append(Paragraph(para, body_style))
            story.append(PageBreak())

        # ---- 4. Chapters ----
        for ch in project.chapters:
            ch_num = ch.index + 1
            ch_title = f"Chapter {ch_num}: {ch.title}"

            # Each chapter starts on a new page
            story.append(PageBreak())
            story.append(Paragraph(ch_title, chapter_title_style))
            story.append(Spacer(1, 6))

            if ch.content_markdown:
                chapter_text = _strip_md(ch.content_markdown)
                for para in chapter_text.split("\n\n"):
                    para = para.strip()
                    if not para:
                        continue
                    para = para.replace("\n", " ")
                    story.append(Paragraph(para, body_style))
            else:
                story.append(Paragraph("[Chapter not yet generated]", body_style))

        # ---- 5. Back matter ----
        if project.backmatter:
            story.append(PageBreak())
            story.append(Paragraph("Back Matter", chapter_title_style))
            story.append(Spacer(1, 12))
            backmatter_text = _strip_md(project.backmatter)
            for para in backmatter_text.split("\n\n"):
                para = para.strip()
                if not para:
                    continue
                para = para.replace("\n", " ")
                story.append(Paragraph(para, body_style))

        # --- Build PDF ---
        doc = SimpleDocTemplate(
            str(file_path),
            pagesize=letter,
            leftMargin=1 * inch,
            rightMargin=1 * inch,
            topMargin=1 * inch,
            bottomMargin=1 * inch,
        )
        doc.build(story, onFirstPage=_add_page_number, onLaterPages=_add_page_number)

        return "DONE"