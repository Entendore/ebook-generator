"""AI-powered consistency checker for generated book content.

Reviews chapters for plot holes, character inconsistencies, timeline errors,
and continuity violations. Provides structured markdown reports that can be
converted to HTML for display in the UI.

This module has no Qt dependencies — all logic is pure Python, designed
to be called from a QThread or any async context.
"""

from __future__ import annotations

import logging
import re
from typing import Optional, Callable

from ..models.book_project import BookProject
from .llm_backend import LLMBackend
from .prompt_engineer import PromptEngineer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

CHAPTER_CONSISTENCY_SYSTEM_PROMPT = (
    "You are a developmental editor and continuity checker. Review the following "
    "chapter for: (1) Plot holes or logical inconsistencies, (2) Character "
    "behavior that contradicts earlier established traits, (3) Timeline or "
    "setting inconsistencies, (4) Unresolved plot threads that were promised, "
    "(5) Repetitive phrases or redundant scenes. For each issue found, cite the "
    "specific text and explain why it's a problem."
)

OUTLINE_VS_CONTENT_SYSTEM_PROMPT = (
    "Compare the book outline with the generated chapters. List any significant "
    "deviations where the generated content doesn't match the planned outline."
)

FULL_BOOK_SYSTEM_PROMPT = (
    "You are a senior developmental editor performing a full-book consistency "
    "audit. Review all chapters for: (1) Plot holes or logical inconsistencies "
    "across the entire narrative, (2) Character behavior that contradicts "
    "earlier established traits or arcs, (3) Timeline or setting inconsistencies "
    "between chapters, (4) Unresolved plot threads that were promised, "
    "(5) Repetitive phrases or redundant scenes across chapters, (6) Tone or "
    "voice shifts that feel unintentional. For each issue found, cite the "
    "specific text and explain why it's a problem."
)


class ConsistencyChecker:
    """AI-powered consistency and continuity checker for book projects.

    Performs analytical reviews of generated content against the world bible,
    previous chapter summaries, and the project outline. Designed to be
    instantiated once and called from a worker thread.

    Args:
        llm: An LLMBackend instance for text generation.
        prompt_engineer: A PromptEngineer instance (kept for potential future
            use in assembling context-aware prompts).
    """

    def __init__(
        self,
        llm: LLMBackend,
        prompt_engineer: PromptEngineer,
    ) -> None:
        self._llm = llm
        self._prompt_engineer = prompt_engineer

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_chapter_consistency(
        self,
        project: BookProject,
        chapter_index: int,
        callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Check a single chapter against world bible, previous summaries, and outline.

        Args:
            project: The book project containing all chapters and metadata.
            chapter_index: Zero-based index of the chapter to check.
            callback: Optional progress callback, called with status strings.

        Returns:
            A structured markdown consistency report.
        """
        chapter = project.get_chapter(chapter_index)
        if chapter is None:
            return f"# Consistency Report\n\n**Error:** Chapter {chapter_index + 1} does not exist."
        if not chapter.content_markdown:
            return (
                f"# Consistency Report: Chapter {chapter_index + 1} - \"{chapter.title}\"\n\n"
                "**Error:** This chapter has no generated content to review."
            )

        self._emit(callback, f"Checking Chapter {chapter_index + 1}: \"{chapter.title}\"...")

        user_prompt = self._build_chapter_prompt(project, chapter_index)

        report = self._llm.generate(
            system_prompt=CHAPTER_CONSISTENCY_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.3,
            top_p=0.9,
            max_tokens=4096,
            stream=False,
        )

        # Wrap the raw LLM output in our standard report header
        header = f"# Consistency Report: Chapter {chapter_index + 1} - \"{chapter.title}\"\n\n"

        self._emit(callback, f"Chapter {chapter_index + 1} check complete.")
        return header + report

    def check_full_book(
        self,
        project: BookProject,
        callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Run consistency checks across all generated chapters.

        Iterates through every chapter that has generated content, collects
        per-chapter findings, and then performs a cross-chapter synthesis
        for issues that span multiple chapters.

        Args:
            project: The book project.
            callback: Optional progress callback.

        Returns:
            A comprehensive markdown report covering all chapters.
        """
        generated_chapters = [
            ch for ch in project.chapters if ch.content_generated and ch.content_markdown
        ]

        if not generated_chapters:
            return "# Full Book Consistency Report\n\nNo generated chapters found to review."

        self._emit(callback, f"Starting full book check ({len(generated_chapters)} chapters)...")

        # --- Per-chapter analysis ---
        per_chapter_reports: list[str] = []
        for ch in generated_chapters:
            self._emit(
                callback,
                f"Analyzing Chapter {ch.index + 1}: \"{ch.title}\"...",
            )

            user_prompt = self._build_chapter_prompt(project, ch.index)
            report = self._llm.generate(
                system_prompt=CHAPTER_CONSISTENCY_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.3,
                top_p=0.9,
                max_tokens=4096,
                stream=False,
            )
            per_chapter_reports.append(
                f"## Chapter {ch.index + 1} - \"{ch.title}\"\n\n{report}"
            )

        # --- Cross-chapter synthesis ---
        self._emit(callback, "Running cross-chapter consistency synthesis...")
        synthesis = self._run_cross_chapter_synthesis(project, generated_chapters)

        # --- Assemble final report ---
        parts: list[str] = [
            f"# Full Book Consistency Report: \"{project.metadata.title}\"\n",
            f"**Total Chapters Reviewed:** {len(generated_chapters)}\n",
            f"**Book Type:** {project.ebook_type.value}\n",
            "",
            "---\n",
        ]
        parts.extend(per_chapter_reports)
        parts.append("\n---\n")
        parts.append("## Cross-Chapter Analysis\n\n")
        parts.append(synthesis)
        parts.append("\n")

        self._emit(callback, "Full book consistency check complete.")
        return "\n".join(parts)

    def check_outline_vs_content(
        self,
        project: BookProject,
        callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Compare the outline with generated chapter content to find deviations.

        Builds a side-by-side prompt containing the outline and all generated
        chapter synopses/content, then asks the LLM to identify where the
        actual content diverges from the plan.

        Args:
            project: The book project.
            callback: Optional progress callback.

        Returns:
            A markdown report listing outline-content deviations.
        """
        if not project.outline:
            return "# Outline vs Content Report\n\n**Error:** No outline has been generated yet."

        generated_chapters = [
            ch for ch in project.chapters if ch.content_generated and ch.content_markdown
        ]

        if not generated_chapters:
            return "# Outline vs Content Report\n\n**Error:** No generated chapters to compare against."

        self._emit(callback, "Comparing outline to generated content...")

        user_prompt = self._build_outline_comparison_prompt(project, generated_chapters)

        report = self._llm.generate(
            system_prompt=OUTLINE_VS_CONTENT_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.3,
            top_p=0.9,
            max_tokens=4096,
            stream=False,
        )

        header = f"# Outline vs Content Report: \"{project.metadata.title}\"\n\n"
        header += f"**Chapters Compared:** {len(generated_chapters)}\n\n---\n\n"

        self._emit(callback, "Outline comparison complete.")
        return header + report

    # ------------------------------------------------------------------
    # Prompt construction (private)
    # ------------------------------------------------------------------

    def _build_chapter_prompt(self, project: BookProject, chapter_index: int) -> str:
        """Assemble the user prompt for checking a single chapter."""
        chapter = project.get_chapter(chapter_index)
        if chapter is None:
            return ""

        parts: list[str] = []

        # World bible context
        world_bible_text = ""
        if project.world_bible is not None:
            world_bible_text = project.world_bible.to_context_text(chapter_index)
        if world_bible_text:
            parts.append("## World Bible Reference\n")
            parts.append(world_bible_text)
            parts.append("")

        # Previous chapter summaries
        summaries = self._collect_previous_summaries(project, chapter_index)
        if summaries:
            parts.append("## Previous Chapter Summaries\n")
            parts.append(summaries)
            parts.append("")

        # Outline excerpt
        outline_excerpt = self._extract_outline_excerpt(project.outline, chapter_index)
        if outline_excerpt:
            parts.append("## Relevant Outline\n")
            parts.append(outline_excerpt)
            parts.append("")

        # The chapter content under review
        parts.append("## Chapter Under Review\n")
        parts.append(f"**Chapter {chapter_index + 1}: {chapter.title}**\n")
        parts.append(chapter.content_markdown)
        parts.append("")

        # Instructions for the format
        parts.append(
            "## Instructions\n"
            "Format your findings as follows:\n"
            "1. Start with a count: \"## Issues Found: N\"\n"
            "2. For each issue, use: \"### Issue N: [Brief Title]\"\n"
            "   - **Severity:** High / Medium / Low\n"
            "   - **Location:** [Where in the chapter]\n"
            "   - **Description:** [Explanation with quoted text]\n"
            "   - **Suggestion:** [How to fix it]\n"
            "3. End with a \"## Positive Notes\" section listing what works well.\n"
            "Be specific. Quote the exact text that has the issue."
        )

        return "\n".join(parts)

    def _build_outline_comparison_prompt(
        self,
        project: BookProject,
        generated_chapters: list,
    ) -> str:
        """Assemble the user prompt for outline-vs-content comparison."""
        parts: list[str] = []

        # The full outline
        parts.append("## Book Outline (Planned)\n")
        parts.append(project.outline)
        parts.append("")

        # Generated chapter summaries/content
        parts.append("## Generated Chapter Content\n")
        for ch in generated_chapters:
            # Use synopsis + a content excerpt to stay within token limits
            parts.append(f"### Chapter {ch.index + 1}: {ch.title}")
            if ch.synopsis:
                parts.append(f"Planned synopsis: {ch.synopsis}")
            # Include first ~3000 chars of content as representative excerpt
            content_excerpt = ch.content_markdown[:3000]
            if len(ch.content_markdown) > 3000:
                content_excerpt += "\n[... content truncated for length ...]"
            parts.append(f"Generated content:\n{content_excerpt}")
            parts.append("")

        parts.append(
            "## Instructions\n"
            "For each chapter, compare the outline plan with the actual content. "
            "List significant deviations such as:\n"
            "- Events or scenes that appear in content but not in the outline\n"
            "- Planned events from the outline that are missing from the content\n"
            "- Different character actions or outcomes than planned\n"
            "- Tone or theme shifts from the outline's intent\n\n"
            "Format each finding as:\n"
            "### Chapter N: [Title]\n"
            "- **Planned:** [What the outline said]\n"
            "- **Actual:** [What the content shows]\n"
            "- **Severity:** Major / Minor / Cosmetic\n\n"
            "End with a summary of overall adherence to the outline."
        )

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Cross-chapter synthesis (private)
    # ------------------------------------------------------------------

    def _run_cross_chapter_synthesis(
        self,
        project: BookProject,
        generated_chapters: list,
    ) -> str:
        """Ask the LLM to find issues that span multiple chapters."""
        parts: list[str] = []

        # Collect concise summaries of each chapter for the synthesis prompt
        parts.append("## Chapter Summaries\n")
        for ch in generated_chapters:
            # Use stored summary if available, otherwise truncate content
            summary = ""
            if ch.generation_notes and "SUMMARY:" in ch.generation_notes:
                summary = ch.generation_notes.split("SUMMARY:", 1)[1].strip()
            if not summary:
                summary = ch.content_markdown[:800]
                if len(ch.content_markdown) > 800:
                    summary += "..."
            parts.append(
                f"- **Chapter {ch.index + 1}: {ch.title}** — {summary}"
            )
        parts.append("")

        # World bible
        world_bible_text = ""
        if project.world_bible is not None:
            world_bible_text = project.world_bible.to_context_text()
        if world_bible_text:
            parts.append("## World Bible\n")
            parts.append(world_bible_text)
            parts.append("")

        parts.append(
            "## Instructions\n"
            "Based on the chapter summaries above, identify any CONSISTENCY ISSUES "
            "THAT SPAN MULTIPLE CHAPTERS, such as:\n"
            "- A character's personality or knowledge changing between chapters\n"
            "- Events referenced in a later chapter that contradict an earlier one\n"
            "- Items or locations that appear/disappear inconsistently\n"
            "- The overall plot arc not connecting as intended\n\n"
            "Format each issue as:\n"
            "### Cross-Chapter Issue: [Title]\n"
            "- **Severity:** High / Medium / Low\n"
            "- **Chapters Involved:** [Chapter numbers]\n"
            "- **Description:** [Detailed explanation]\n"
            "- **Suggestion:** [How to resolve]\n\n"
            "If no cross-chapter issues are found, say \"No cross-chapter issues found.\" "
            "Then list positive observations about the narrative coherence."
        )

        user_prompt = "\n".join(parts)

        return self._llm.generate(
            system_prompt=FULL_BOOK_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.3,
            top_p=0.9,
            max_tokens=4096,
            stream=False,
        )

    # ------------------------------------------------------------------
    # Helpers (private)
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_previous_summaries(project: BookProject, chapter_index: int) -> str:
        """Gather stored summaries for chapters before *chapter_index*."""
        summaries: list[str] = []
        for i in range(chapter_index):
            ch = project.get_chapter(i)
            if ch is None:
                continue
            summary = ""
            if ch.generation_notes and "SUMMARY:" in ch.generation_notes:
                summary = ch.generation_notes.split("SUMMARY:", 1)[1].strip()
            if not summary and ch.content_markdown:
                # Fallback: use first 300 chars as a rough summary
                summary = ch.content_markdown[:300]
                if len(ch.content_markdown) > 300:
                    summary += "..."
            if summary:
                summaries.append(f"Chapter {i + 1}: {summary}")
        return "\n".join(summaries) if summaries else ""

    @staticmethod
    def _extract_outline_excerpt(outline: str, chapter_index: int) -> str:
        """Extract the outline section relevant to a given chapter."""
        if not outline:
            return ""

        lines = outline.split("\n")

        # Try to find the specific chapter heading in the outline
        for i, line in enumerate(lines):
            if f"chapter {chapter_index + 1}" in line.lower():
                start = max(0, i - 2)
                end = min(len(lines), i + 15)
                return "\n".join(lines[start:end])

        # Fallback: return first 30 lines for chapter 1, or a small window
        if chapter_index == 0:
            return "\n".join(lines[:30])
        return "\n".join(lines[:15])

    @staticmethod
    def _emit(
        callback: Optional[Callable[[str], None]],
        message: str,
    ) -> None:
        """Safely call the progress callback."""
        if callback is not None:
            try:
                callback(message)
            except Exception:
                logger.debug("Consistency checker callback raised an exception.", exc_info=True)

    # ------------------------------------------------------------------
    # HTML conversion (static, for QTextEdit display)
    # ------------------------------------------------------------------

    @staticmethod
    def format_report_as_html(report_md: str) -> str:
        """Convert a markdown consistency report to simple HTML.

        Handles: ``#`` headers, ``###`` subheaders, ``**bold**``, ``-`` bullets,
        and adds colour highlighting for severity levels (High / Medium / Low).

        The output is designed for display in a QTextEdit or similar rich-text
        widget. No external CSS is required.

        Args:
            report_md: The markdown report string.

        Returns:
            An HTML string with inline styles.
        """
        if not report_md:
            return "<p><em>No report available.</em></p>"

        html_lines: list[str] = []
        # Wrap everything in a styled container
        html_lines.append(
            '<div style="font-family: sans-serif; font-size: 13px; '
            'line-height: 1.6; color: #e0e0e0; padding: 8px;">'
        )

        lines = report_md.split("\n")

        # Track whether we're inside a list
        in_list = False

        for line in lines:
            stripped = line.strip()

            # Skip empty lines — close any open list
            if not stripped:
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                html_lines.append("<br/>")
                continue

            # --- Headers ---
            if stripped.startswith("#### "):
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                text = stripped[5:]
                text = ConsistencyChecker._inline_markdown_to_html(text)
                html_lines.append(
                    f'<h4 style="font-size: 13px; font-weight: bold; '
                    f'color: #b0b0b0; margin: 12px 0 4px 0;">{text}</h4>'
                )
                continue

            if stripped.startswith("### "):
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                text = stripped[4:]
                text = ConsistencyChecker._inline_markdown_to_html(text)
                html_lines.append(
                    f'<h3 style="font-size: 14px; font-weight: bold; '
                    f'color: #d4d4d4; margin: 16px 0 6px 0; '
                    f'border-bottom: 1px solid #444; padding-bottom: 3px;">'
                    f'{text}</h3>'
                )
                continue

            if stripped.startswith("## "):
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                text = stripped[3:]
                text = ConsistencyChecker._inline_markdown_to_html(text)
                html_lines.append(
                    f'<h2 style="font-size: 16px; font-weight: bold; '
                    f'color: #ffffff; margin: 20px 0 8px 0;">{text}</h2>'
                )
                continue

            if stripped.startswith("# "):
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                text = stripped[2:]
                text = ConsistencyChecker._inline_markdown_to_html(text)
                html_lines.append(
                    f'<h1 style="font-size: 20px; font-weight: bold; '
                    f'color: #ffffff; margin: 0 0 10px 0;">{text}</h1>'
                )
                continue

            # --- Horizontal rule ---
            if stripped.startswith("---"):
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                html_lines.append(
                    '<hr style="border: none; border-top: 1px solid #555; '
                    'margin: 16px 0;" />'
                )
                continue

            # --- Bullet lists ---
            if stripped.startswith("- ") or stripped.startswith("* "):
                if not in_list:
                    html_lines.append(
                        '<ul style="margin: 4px 0 4px 20px; padding: 0; '
                        'list-style-type: disc;">'
                    )
                    in_list = True
                text = stripped[2:]
                text = ConsistencyChecker._inline_markdown_to_html(text)
                # Severity colour highlighting
                text = ConsistencyChecker._highlight_severity(text)
                html_lines.append(f'<li style="margin: 2px 0;">{text}</li>')
                continue

            # --- Ordered list items (e.g., "1. ...") ---
            if re.match(r"^\d+\.\s", stripped):
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                text = ConsistencyChecker._inline_markdown_to_html(stripped)
                text = ConsistencyChecker._highlight_severity(text)
                html_lines.append(f'<p style="margin: 2px 0 2px 20px;">{text}</p>')
                continue

            # --- Regular paragraphs ---
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            text = ConsistencyChecker._inline_markdown_to_html(stripped)
            text = ConsistencyChecker._highlight_severity(text)
            html_lines.append(f"<p style=\"margin: 4px 0;\">{text}</p>")

        # Close any remaining list
        if in_list:
            html_lines.append("</ul>")

        html_lines.append("</div>")
        return "\n".join(html_lines)

    # ------------------------------------------------------------------
    # HTML helpers (private static)
    # ------------------------------------------------------------------

    @staticmethod
    def _inline_markdown_to_html(text: str) -> str:
        """Convert **bold** and *italic* inline markdown to HTML."""
        # Bold: **text**
        text = re.sub(
            r"\*\*(.+?)\*\*",
            r'<strong style="color: #ffffff;">\1</strong>',
            text,
        )
        # Italic: *text* (but not inside already-processed <strong> tags)
        text = re.sub(
            r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)",
            r"<em>\1</em>",
            text,
        )
        # Inline code: `text`
        text = re.sub(
            r"`(.+?)`",
            r'<code style="background: #333; padding: 1px 4px; '
            r'border-radius: 3px; font-size: 12px;">\1</code>',
            text,
        )
        return text

    @staticmethod
    def _highlight_severity(text: str) -> str:
        """Add colour spans for severity keywords: High, Medium, Low."""
        text = re.sub(
            r"\bHigh\b",
            '<span style="color: #f85149; font-weight: bold;">High</span>',
            text,
        )
        text = re.sub(
            r"\bMedium\b",
            '<span style="color: #d29922; font-weight: bold;">Medium</span>',
            text,
        )
        text = re.sub(
            r"\bLow\b",
            '<span style="color: #3fb950; font-weight: bold;">Low</span>',
            text,
        )
        # Also highlight Major/Minor/Cosmetic for outline comparisons
        text = re.sub(
            r"\bMajor\b",
            '<span style="color: #f85149; font-weight: bold;">Major</span>',
            text,
        )
        text = re.sub(
            r"\bMinor\b",
            '<span style="color: #d29922; font-weight: bold;">Minor</span>',
            text,
        )
        text = re.sub(
            r"\bCosmetic\b",
            '<span style="color: #3fb950; font-weight: bold;">Cosmetic</span>',
            text,
        )
        return text