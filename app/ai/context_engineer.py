"""Context engineering system for long-form ebook generation.

Manages the LLM's context window to maintain narrative consistency
across a full book. Implements four strategies:

1. **Rolling Summary** — Each generated chapter is summarized, and
   previous chapter summaries are fed as context for the next chapter.
   Most token-efficient; best for long books with limited context windows.

2. **Full Context** — Passes all previously generated chapter text
   directly. Highest quality but requires a large context window.

3. **Sliding Window** — Keeps the last N full chapters plus summaries
   of earlier chapters. A balanced approach between quality and efficiency.

4. **Hybrid** — Combines world bible, summaries of old chapters,
   and full text of recent chapters. Best overall quality when
   a world bible is populated.

The ContextEngineer also handles token counting, context budgeting,
and intelligent truncation to stay within the model's context limit.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from ..models.book_project import BookProject, Chapter, EbookType

logger = logging.getLogger(__name__)


@dataclass
class ContextBudget:
    """Tracks how the context window is allocated."""
    total_tokens: int = 8192
    system_prompt_tokens: int = 0
    user_prompt_tokens: int = 0
    context_tokens: int = 0
    reserved_for_generation: int = 4096

    @property
    def available_for_context(self) -> int:
        """Tokens available for historical context (previous chapters)."""
        used = self.system_prompt_tokens + self.user_prompt_tokens + self.reserved_for_generation
        return max(0, self.total_tokens - used)


@dataclass
class ChapterContext:
    """Prepared context for generating a specific chapter."""
    previous_summary: str = ""
    sliding_window_text: str = ""
    outline_excerpt: str = ""
    character_bible: str = ""
    world_notes: str = ""
    total_context_tokens: int = 0


class ContextEngineer:
    """Manages context window allocation for coherent long-form generation.

    Usage:
        engineer = ContextEngineer(llm_backend, strategy="rolling_summary")
        engineer.set_project(project)
        context = engineer.build_context_for_chapter(chapter_index)
    """

    STRATEGIES = ("rolling_summary", "full_context", "sliding_window", "hybrid")

    def __init__(
        self,
        count_tokens_fn=None,  # callable: str -> int
        strategy: str = "rolling_summary",
        sliding_window_size: int = 3,
        total_context_tokens: int = 8192,
    ) -> None:
        self._count_tokens = count_tokens_fn or self._estimate_tokens
        self._strategy = strategy
        self._sliding_window_size = sliding_window_size
        self._total_context_tokens = total_context_tokens
        self._chapter_summaries: dict[int, str] = {}
        self._project: Optional[BookProject] = None

    def set_context_size(self, n_ctx: int) -> None:
        """Update the total context window size to match the loaded model."""
        self._total_context_tokens = n_ctx
        logger.info("ContextEngineer context size set to %d tokens", n_ctx)

    @property
    def total_context_tokens(self) -> int:
        return self._total_context_tokens

    @property
    def strategy(self) -> str:
        return self._strategy

    @strategy.setter
    def strategy(self, value: str) -> None:
        if value not in self.STRATEGIES:
            raise ValueError(f"Unknown strategy: {value}. Choose from {self.STRATEGIES}")
        self._strategy = value

    def set_project(self, project: BookProject) -> None:
        """Associate this engineer with a book project."""
        self._project = project
        # Restore any existing summaries from chapter notes
        for ch in project.chapters:
            if ch.generation_notes and "SUMMARY:" in ch.generation_notes:
                summary_part = ch.generation_notes.split("SUMMARY:", 1)[1].strip()
                self._chapter_summaries[ch.index] = summary_part
        # Update strategy if it's not valid
        if self._strategy not in self.STRATEGIES:
            self._strategy = "rolling_summary"

    def store_summary(self, chapter_index: int, summary: str) -> None:
        """Store a chapter summary for later use in context."""
        self._chapter_summaries[chapter_index] = summary
        # Also persist to the chapter object
        if self._project:
            ch = self._project.get_chapter(chapter_index)
            if ch:
                if "SUMMARY:" in ch.generation_notes:
                    ch.generation_notes = ch.generation_notes.split("SUMMARY:")[0].rstrip()
                ch.generation_notes += f"\nSUMMARY: {summary}"

    def get_summary(self, chapter_index: int) -> str:
        """Retrieve a stored chapter summary."""
        return self._chapter_summaries.get(chapter_index, "")

    def build_context_for_chapter(
        self,
        chapter_index: int,
        system_prompt: str = "",
        user_prompt_template: str = "",
        reserved_generation_tokens: int = 4096,
    ) -> ChapterContext:
        """Build the optimal context for generating a given chapter.

        Args:
            chapter_index: Index of the chapter to be generated.
            system_prompt: The system prompt that will be used.
            user_prompt_template: The user prompt template (before filling).
            reserved_generation_tokens: Tokens to reserve for the output.

        Returns:
            A ChapterContext with all the context pieces assembled.
        """
        if self._project is None:
            return ChapterContext()

        budget = ContextBudget(
            total_tokens=self._total_context_tokens,
            system_prompt_tokens=self._count_tokens(system_prompt),
            user_prompt_tokens=self._count_tokens(user_prompt_template),
            reserved_for_generation=reserved_generation_tokens,
        )

        available = budget.available_for_context

        if self._strategy == "rolling_summary":
            return self._build_rolling_summary_context(chapter_index, available)
        elif self._strategy == "full_context":
            return self._build_full_context(chapter_index, available)
        elif self._strategy == "sliding_window":
            return self._build_sliding_window_context(chapter_index, available)
        elif self._strategy == "hybrid":
            return self._build_hybrid_context(chapter_index, available)
        return ChapterContext()

    # ------------------------------------------------------------------
    # Strategy: Rolling Summary
    # ------------------------------------------------------------------

    def _build_rolling_summary_context(
        self, chapter_index: int, token_budget: int
    ) -> ChapterContext:
        """Use only summaries of previous chapters as context."""
        summaries = []
        tokens_used = 0
        for i in range(chapter_index):
            summary = self._chapter_summaries.get(i, "")
            if not summary and self._project:
                ch = self._project.get_chapter(i)
                if ch and ch.content_markdown:
                    summary = f"[Chapter {i+1}: {ch.title}] (summary not yet generated)"
            if summary:
                summary_text = f"Chapter {i+1}: {summary}"
                summary_tokens = self._count_tokens(summary_text)
                if tokens_used + summary_tokens <= token_budget:
                    summaries.append(summary_text)
                    tokens_used += summary_tokens
                else:
                    remaining = chapter_index - i
                    summaries.append(f"[{remaining} earlier chapters summarized above]")
                    break

        previous_summary = "\n".join(summaries) if summaries else ""
        outline_excerpt = self._extract_outline_excerpt(chapter_index, token_budget - tokens_used)

        return ChapterContext(
            previous_summary=previous_summary,
            outline_excerpt=outline_excerpt,
            total_context_tokens=tokens_used + self._count_tokens(outline_excerpt),
        )

    # ------------------------------------------------------------------
    # Strategy: Full Context
    # ------------------------------------------------------------------

    def _build_full_context(
        self, chapter_index: int, token_budget: int
    ) -> ChapterContext:
        """Pass full text of all previous chapters."""
        if not self._project:
            return ChapterContext()

        chunks = []
        tokens_used = 0
        for i in range(chapter_index):
            ch = self._project.get_chapter(i)
            if ch and ch.content_markdown:
                header = f"\n--- Chapter {i+1}: {ch.title} ---\n"
                full_text = header + ch.content_markdown
                text_tokens = self._count_tokens(full_text)
                if tokens_used + text_tokens <= token_budget:
                    chunks.append(full_text)
                    tokens_used += text_tokens
                else:
                    remaining = token_budget - tokens_used
                    truncated = full_text[:remaining * 4]
                    chunks.append(truncated + "\n[... truncated due to context limit ...]")
                    break

        outline_excerpt = self._extract_outline_excerpt(chapter_index, token_budget - tokens_used)

        return ChapterContext(
            previous_summary="",
            sliding_window_text="\n".join(chunks),
            outline_excerpt=outline_excerpt,
            total_context_tokens=tokens_used,
        )

    # ------------------------------------------------------------------
    # Strategy: Sliding Window
    # ------------------------------------------------------------------

    def _build_sliding_window_context(
        self, chapter_index: int, token_budget: int
    ) -> ChapterContext:
        """Keep last N full chapters + summaries of earlier ones."""
        if not self._project:
            return ChapterContext()

        window_start = max(0, chapter_index - self._sliding_window_size)
        tokens_used = 0

        early_summaries = []
        for i in range(window_start):
            summary = self._chapter_summaries.get(i, "")
            if summary:
                text = f"Ch.{i+1}: {summary}"
                t = self._count_tokens(text)
                if tokens_used + t <= token_budget // 3:
                    early_summaries.append(text)
                    tokens_used += t

        window_chapters = []
        for i in range(window_start, chapter_index):
            ch = self._project.get_chapter(i)
            if ch and ch.content_markdown:
                header = f"\n--- Chapter {i+1}: {ch.title} ---\n"
                full_text = header + ch.content_markdown
                text_tokens = self._count_tokens(full_text)
                if tokens_used + text_tokens <= token_budget:
                    window_chapters.append(full_text)
                    tokens_used += text_tokens
                else:
                    remaining = token_budget - tokens_used
                    truncated = full_text[:remaining * 4]
                    window_chapters.append(truncated + "\n[... truncated ...]")
                    break

        outline_excerpt = self._extract_outline_excerpt(chapter_index, token_budget - tokens_used)

        combined = ""
        if early_summaries:
            combined += "Earlier chapters (summarized):\n" + "\n".join(early_summaries) + "\n\n"
        if window_chapters:
            combined += "Recent chapters (full text):\n" + "\n".join(window_chapters)

        return ChapterContext(
            previous_summary="\n".join(early_summaries) if early_summaries else "",
            sliding_window_text=combined,
            outline_excerpt=outline_excerpt,
            total_context_tokens=tokens_used,
        )

    # ------------------------------------------------------------------
    # Strategy: Hybrid (summaries + recent full chapters + world bible)
    # ------------------------------------------------------------------

    def _build_hybrid_context(
        self, chapter_index: int, token_budget: int
    ) -> ChapterContext:
        """Best-of-all-worlds: world bible + summaries + recent full chapters."""
        if not self._project:
            return ChapterContext()
        tokens_used = 0

        # 1. World bible (if available)
        if (self._project.world_bible is not None
                and self._project.world_bible.entries):
            wb_text = self._project.world_bible.to_context_text(chapter_index)
            if wb_text:
                wb_tokens = self._count_tokens(wb_text)
                if wb_tokens < token_budget * 0.15:
                    tokens_used += wb_tokens

        # 2. Summaries of chapters before the window
        window_start = max(0, chapter_index - self._sliding_window_size)
        early_summaries = []
        for i in range(window_start):
            summary = self._chapter_summaries.get(i, "")
            if summary:
                text = f"Ch.{i+1}: {summary}"
                t = self._count_tokens(text)
                if tokens_used + t < token_budget * 0.45:
                    early_summaries.append(text)
                    tokens_used += t

        # 3. Full text of recent chapters
        window_chapters = []
        for i in range(window_start, chapter_index):
            ch = self._project.get_chapter(i)
            if ch and ch.content_markdown:
                header = "\n--- Chapter " + str(i + 1) + ": " + ch.title + " ---\n"
                full_text = header + ch.content_markdown
                text_tokens = self._count_tokens(full_text)
                remaining = token_budget - tokens_used
                if remaining > 0 and text_tokens < remaining * 0.7:
                    window_chapters.append(full_text)
                    tokens_used += text_tokens
                elif remaining > 0:
                    window_chapters.append(full_text[:remaining * 3] + "\n[... truncated ...]")
                    break

        combined = ""
        if early_summaries:
            combined += "Earlier chapters (summarized):\n" + "\n".join(early_summaries) + "\n\n"
        if window_chapters:
            combined += "Recent chapters (full text):\n" + "\n".join(window_chapters)

        outline_excerpt = self._extract_outline_excerpt(chapter_index, token_budget - tokens_used)

        return ChapterContext(
            previous_summary="\n".join(early_summaries) if early_summaries else "",
            sliding_window_text=combined,
            outline_excerpt=outline_excerpt,
            total_context_tokens=tokens_used,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_outline_excerpt(
        self, chapter_index: int, token_budget: int
    ) -> str:
        """Extract the relevant portion of the outline for a chapter."""
        if not self._project or not self._project.outline:
            return ""

        outline = self._project.outline
        lines = outline.split("\n")

        target_lines = []
        for i, line in enumerate(lines):
            if f"chapter {chapter_index + 1}" in line.lower() or (
                chapter_index + 1 == 1 and i < 20
            ):
                start = max(0, i - 2)
                end = min(len(lines), i + 15)
                target_lines = lines[start:end]
                break

        if not target_lines:
            excerpt = "\n".join(lines[:30])
        else:
            excerpt = "\n".join(target_lines)

        if self._count_tokens(excerpt) > token_budget:
            excerpt = excerpt[:token_budget * 4]
        return excerpt

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Rough token estimate: ~4 chars per token for English."""
        return len(text) // 4

    def get_context_report(self, chapter_index: int) -> str:
        """Generate a human-readable report of the context that would be used."""
        ctx = self.build_context_for_chapter(chapter_index)
        parts = []
        parts.append(f"Strategy: {self._strategy}")
        parts.append(f"Estimated context tokens: {ctx.total_context_tokens}")
        if ctx.previous_summary:
            parts.append(f"Previous summary length: {len(ctx.previous_summary)} chars")
        if ctx.sliding_window_text:
            parts.append(f"Sliding window text length: {len(ctx.sliding_window_text)} chars")
        if ctx.outline_excerpt:
            parts.append(f"Outline excerpt length: {len(ctx.outline_excerpt)} chars")
        parts.append(f"Stored summaries: {len(self._chapter_summaries)} chapters")
        return "\n".join(parts)