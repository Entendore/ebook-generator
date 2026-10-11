"""EPUB exporter — outputs the complete book as a standard .epub file.

Uses the `ebooklib` library to create a valid EPUB 3.0 document with:
- Cover metadata
- Table of contents
- Front matter, chapters, and back matter as separate XHTML sections
- Basic styling for readable typography
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from ..models.book_project import BookProject, EBOOK_TYPE_LABELS

logger = logging.getLogger(__name__)

# Minimal CSS for the EPUB
_EPUB_CSS = """
body {
    font-family: Georgia, "Times New Roman", serif;
    font-size: 1.1em;
    line-height: 1.8;
    margin: 1.5em;
    color: #222;
    max-width: 100%;
}
h1 { font-size: 2em; margin: 1.5em 0 0.5em 0; text-align: center; }
h2 { font-size: 1.5em; margin: 1.5em 0 0.5em 0; page-break-before: always; }
h3 { font-size: 1.2em; margin: 1em 0 0.3em 0; }
p { margin: 0.8em 0; text-indent: 1.5em; }
p:first-child { text-indent: 0; }
blockquote {
    margin: 1em 2em;
    font-style: italic;
    border-left: 3px solid #ccc;
    padding-left: 1em;
}
code {
    font-family: "Courier New", monospace;
    background-color: #f4f4f4;
    padding: 2px 4px;
    font-size: 0.9em;
}
pre {
    background-color: #f4f4f4;
    padding: 1em;
    margin: 1em 0;
    white-space: pre-wrap;
    font-size: 0.9em;
}
hr { margin: 2em 0; border: none; border-top: 1px solid #ccc; }
em { font-style: italic; }
strong { font-weight: bold; }
"""


def _markdown_to_simple_html(md_text: str) -> str:
    """Convert basic Markdown to simple HTML for EPUB embedding.

    Handles: headers, bold, italic, code blocks, horizontal rules,
    paragraphs, and line breaks. Does not need to be perfect — the
    EPUB reader will handle the rest.
    """
    import re

    if not md_text:
        return "<p></p>"

    html_lines: list[str] = []
    lines = md_text.split("\n")
    in_code_block = False
    code_buffer: list[str] = []

    for line in lines:
        # Code block toggle
        if line.strip().startswith("```"):
            if in_code_block:
                code_text = "\n".join(code_buffer)
                escaped = code_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                html_lines.append(f"<pre><code>{escaped}</code></pre>")
                code_buffer = []
                in_code_block = False
            else:
                in_code_block = True
            continue

        if in_code_block:
            code_buffer.append(line)
            continue

        stripped = line.strip()

        # Horizontal rule
        if stripped in ("---", "***", "___"):
            html_lines.append("<hr />")
            continue

        # Headers
        if stripped.startswith("### "):
            html_lines.append(f"<h3>{_inline_md(stripped[4:])}</h3>")
            continue
        if stripped.startswith("## "):
            html_lines.append(f"<h2>{_inline_md(stripped[3:])}</h2>")
            continue
        if stripped.startswith("# "):
            html_lines.append(f"<h1>{_inline_md(stripped[2:])}</h1>")
            continue

        # Empty line = paragraph break
        if not stripped:
            html_lines.append("")
            continue

        # Blockquote
        if stripped.startswith("> "):
            html_lines.append(f"<blockquote><p>{_inline_md(stripped[2:])}</p></blockquote>")
            continue

        # Regular paragraph
        html_lines.append(f"<p>{_inline_md(stripped)}</p>")

    # Close any unclosed code block
    if in_code_block and code_buffer:
        code_text = "\n".join(code_buffer)
        escaped = code_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        html_lines.append(f"<pre><code>{escaped}</code></pre>")

    return "\n".join(html_lines)


def _inline_md(text: str) -> str:
    """Convert inline Markdown (bold, italic, code) to HTML."""
    import re
    # Escape HTML first
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # Bold
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    # Italic
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    # Inline code
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    return text


class EpubExporter:
    """Export a BookProject to an EPUB file using ebooklib."""

    @staticmethod
    def export(project: BookProject, file_path: str) -> None:
        try:
            from ebooklib import epub
        except ImportError:
            raise ImportError(
                "ebooklib is not installed. Install it with: pip install ebooklib"
            )

        meta = project.metadata
        type_label = EBOOK_TYPE_LABELS.get(project.ebook_type, "Book")

        # --- Create the book ---
        book = epub.EpubBook()
        book.set_title(meta.title)
        book.set_language(meta.language or "en")
        book.add_author(meta.author)

        if meta.description:
            book.add_metadata("DC", "description", meta.description)
        if meta.publisher:
            book.add_metadata("DC", "publisher", meta.publisher)
        book.add_metadata("DC", "date", datetime.now().strftime("%Y-%m-%d"))

        # Add CSS
        css_item = epub.EpubItem(
            uid="style",
            file_name="style/default.css",
            media_type="text/css",
            content=_EPUB_CSS.encode("utf-8"),
        )
        book.add_item(css_item)

        # --- Build spine and TOC ---
        spine_items: list[str] = ["nav"]
        toc_items: list = []

        # --- Front matter ---
        if project.frontmatter:
            fm_chapter = epub.EpubHtml(
                title="Front Matter",
                file_name="frontmatter.xhtml",
                lang=meta.language or "en",
            )
            fm_chapter.content = _markdown_to_simple_html(project.frontmatter)
            fm_chapter.add_item(css_item)
            book.add_item(fm_chapter)
            spine_items.append(fm_chapter)
            toc_items.append(fm_chapter)

        # --- Title page ---
        title_html = f"<h1>{meta.title}</h1>"
        if meta.subtitle:
            title_html += f"<h2>{meta.subtitle}</h2>"
        title_html += f"<p>by <strong>{meta.author}</strong></p>"
        if meta.description:
            title_html += f"<p><em>{meta.description}</em></p>"

        title_page = epub.EpubHtml(
            title="Title Page",
            file_name="title_page.xhtml",
            lang=meta.language or "en",
        )
        title_page.content = title_html
        title_page.add_item(css_item)
        book.add_item(title_page)
        spine_items.append(title_page)

        # --- Chapters ---
        for ch in project.chapters:
            ch_num = ch.index + 1
            ch_title = f"Chapter {ch_num}: {ch.title}"

            # Build chapter HTML
            ch_html = f"<h2>{ch_title}</h2>\n"
            if ch.synopsis:
                ch_html += f"<p><em>{ch.synopsis}</em></p>\n"
            if ch.content_markdown:
                ch_html += _markdown_to_simple_html(ch.content_markdown)
            else:
                ch_html += "<p><em>[Chapter not yet generated]</em></p>"

            ch_item = epub.EpubHtml(
                title=ch_title,
                file_name=f"chapter_{ch_num:03d}.xhtml",
                lang=meta.language or "en",
            )
            ch_item.content = ch_html
            ch_item.add_item(css_item)
            book.add_item(ch_item)
            spine_items.append(ch_item)
            toc_items.append(ch_item)

        # --- Back matter ---
        if project.backmatter:
            bm_chapter = epub.EpubHtml(
                title="Back Matter",
                file_name="backmatter.xhtml",
                lang=meta.language or "en",
            )
            bm_chapter.content = _markdown_to_simple_html(project.backmatter)
            bm_chapter.add_item(css_item)
            book.add_item(bm_chapter)
            spine_items.append(bm_chapter)
            toc_items.append(bm_chapter)

        # --- Navigation / TOC ---
        book.toc = toc_items

        # Add nav file
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        # Set spine
        book.spine = spine_items

        # --- Write EPUB ---
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        epub.write_epub(str(path), book)
        logger.info("EPUB exported to %s", path)