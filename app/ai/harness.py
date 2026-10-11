"""AI Harness — orchestrates the full ebook generation pipeline.

Enhanced with: multi-pass refinement, single-chapter regeneration,
world bible injection, token usage tracking, retry logic, revision
history, checkpoint/resume, quality gates, adaptive temperature,
chain-of-thought planning, pipeline hooks, dynamic context budgets,
inter-chapter consistency checks, and continue-generation support.
"""

from __future__ import annotations

import json
import logging
import math
import re
import time
import hashlib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable

from PySide6.QtCore import QObject, Signal

from ..models.book_project import (
    BookProject, Chapter, GenerationState, EbookType,
    EBOOK_TYPE_LABELS,
)
from ..models.extended_models import (
    WorldBible, RevisionHistory, RevisionEntry, TokenUsageTracker,
)
from .llm_backend import LLMBackend
from .prompt_engineer import PromptEngineer
from .context_engineer import ContextEngineer

logger = logging.getLogger(__name__)


# ======================================================================
# Quality Gate data structures
# ======================================================================

@dataclass
class QualityReport:
    """Result of a quality gate validation pass."""
    passed: bool = True
    word_count: int = 0
    target_words: int = 0
    repetition_score: float = 0.0  # 0.0 (clean) to 1.0 (very repetitive)
    issues: list[str] = field(default_factory=list)
    score: float = 1.0  # 0.0 to 1.0 overall quality score


@dataclass
class GenerationCheckpoint:
    """Serialisable snapshot of generation progress."""
    completed_chapters: list[int] = field(default_factory=list)
    outline_done: bool = False
    frontmatter_done: bool = False
    backmatter_done: bool = False
    last_completed_step: str = ""
    timestamp: str = field(
        default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S")
    )

    def to_dict(self) -> dict:
        return {
            "completed_chapters": self.completed_chapters,
            "outline_done": self.outline_done,
            "frontmatter_done": self.frontmatter_done,
            "backmatter_done": self.backmatter_done,
            "last_completed_step": self.last_completed_step,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict) -> GenerationCheckpoint:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ======================================================================
# Pipeline Hook types
# ======================================================================

@dataclass
class PipelineHook:
    """A before/after callback attached to a pipeline stage."""
    stage: str  # "outline", "chapter", "frontmatter", "backmatter", "summary", "refine"
    when: str   # "before" or "after"
    callback: Callable = field(repr=False)
    label: str = ""


class AIHarness(QObject):
    """Central orchestration engine for ebook generation.

    Emits Qt signals so the UI can update in real-time.

    Improvements over the original harness:
    - **Checkpoint/Resume**: generation state saved per chapter; resume from
      interruption without re-generating completed chapters.
    - **Quality Gates**: word-count, repetition, and structural validation
      after each chapter with automatic retry on failure.
    - **Adaptive Temperature**: adjusts sampling temperature dynamically
      based on chapter position, previous chapter word counts, and
      ebook type to maintain consistent output length.
    - **Chain-of-Thought Planning**: for complex chapter types, the model
      first produces a short plan/outline before writing, improving
      coherence and structure.
    - **Pipeline Hooks**: register before/after callbacks per stage for
      custom processing (logging, metrics, external integrations).
    - **Dynamic Context Budget**: reserved generation tokens scale with
      chapter position and average previous chapter length.
    - **Inter-Chapter Consistency**: lightweight adjacent-chapter check
      after generation detects glaring inconsistencies.
    - **Continue Generation**: append to an interrupted chapter from
      where it stopped.
    """

    # --- Qt Signals ---
    state_changed = Signal(str)
    progress_changed = Signal(float)
    chapter_started = Signal(int, str)
    chapter_completed = Signal(int)
    chapter_progress = Signal(str)
    outline_generated = Signal(str)
    frontmatter_generated = Signal(str)
    backmatter_generated = Signal(str)
    error_occurred = Signal(str)
    generation_finished = Signal()
    log_message = Signal(str)
    # Extended signals
    refinement_pass = Signal(int, int)       # (current_pass, total_passes)
    single_chapter_done = Signal(int)        # chapter index
    quality_report = Signal(object)          # QualityReport
    checkpoint_saved = Signal(int)           # chapter index
    consistency_check = Signal(int, str)     # (chapter_idx, report_text)

    def __init__(
        self,
        llm: LLMBackend,
        prompt_engineer: PromptEngineer,
        context_engineer: ContextEngineer,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._llm = llm
        self._prompt_eng = prompt_engineer
        self._context_eng = context_engineer
        self._project: Optional[BookProject] = None
        self._cancelled = False
        self._paused = False
        self._current_streamed_text = ""

        # --- New infrastructure ---
        self._hooks: list[PipelineHook] = []
        self._checkpoint: Optional[GenerationCheckpoint] = None
        self._word_count_history: list[int] = []  # per-chapter word counts

        # Adaptive temperature state
        self._target_words: int = 2000
        self._base_temperature: float = 0.75

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def project(self) -> Optional[BookProject]:
        return self._project

    @property
    def checkpoint(self) -> Optional[GenerationCheckpoint]:
        return self._checkpoint

    # ------------------------------------------------------------------
    # Project & model lifecycle
    # ------------------------------------------------------------------

    def set_project(self, project: BookProject) -> None:
        self._project = project
        self._context_eng.set_project(project)

        # Propagate model context size to the context engineer
        if self._llm.is_loaded:
            self._context_eng.set_context_size(self._llm.context_size)
            logger.info(
                "ContextEngineer updated to model context size: %d",
                self._llm.context_size,
            )

        # Restore word count history from already-generated chapters
        self._word_count_history = [
            ch.word_count for ch in project.chapters if ch.content_generated
        ]

        # Restore or create checkpoint
        self._restore_checkpoint(project)

        self.log_message.emit(
            f"Project set: {project.name} "
            f"({EBOOK_TYPE_LABELS.get(project.ebook_type, '?')})"
        )

    # ------------------------------------------------------------------
    # Control: cancel / pause / resume
    # ------------------------------------------------------------------

    def cancel(self) -> None:
        self._cancelled = True
        self.log_message.emit("Generation cancelled by user.")

    def pause(self) -> None:
        self._paused = True
        self.log_message.emit("Generation will pause after current chapter.")

    def resume(self) -> None:
        self._paused = False
        self.log_message.emit("Generation resumed.")

    # ------------------------------------------------------------------
    # Pipeline hooks
    # ------------------------------------------------------------------

    def add_hook(
        self, stage: str, when: str, callback: Callable, label: str = "",
    ) -> None:
        """Register a before/after callback for a pipeline stage.

        Args:
            stage: One of "outline", "chapter", "frontmatter", "backmatter",
                   "summary", "refine", "quality_gate", "consistency_check".
            when: "before" or "after".
            callback: Callable receiving (harness, **kwargs).
            label: Optional human-readable label.
        """
        self._hooks.append(PipelineHook(
            stage=stage, when=when, callback=callback, label=label or callback.__name__,
        ))

    def remove_hook(self, label: str) -> None:
        self._hooks = [h for h in self._hooks if h.label != label]

    def clear_hooks(self) -> None:
        self._hooks.clear()

    def _fire_hooks(self, stage: str, when: str, **kwargs) -> None:
        for hook in self._hooks:
            if hook.stage == stage and hook.when == when:
                try:
                    hook.callback(self, **kwargs)
                except Exception as exc:
                    logger.warning("Hook '%s' failed: %s", hook.label, exc)

    # ------------------------------------------------------------------
    # Checkpoint / Resume
    # ------------------------------------------------------------------

    def _restore_checkpoint(self, project: BookProject) -> None:
        """Restore checkpoint from project generation notes or create fresh."""
        # Try to restore from project-level checkpoint storage
        cp_file = self._checkpoint_path(project)
        if cp_file and Path(cp_file).exists():
            try:
                data = json.loads(Path(cp_file).read_text(encoding="utf-8"))
                self._checkpoint = GenerationCheckpoint.from_dict(data)
                self.log_message.emit(
                    f"Checkpoint restored: {len(self._checkpoint.completed_chapters)} "
                    f"chapters already completed."
                )
                return
            except Exception as exc:
                logger.warning("Failed to restore checkpoint: %s", exc)

        # Build checkpoint from existing generated chapters
        completed = [i for i, ch in enumerate(project.chapters) if ch.content_generated]
        self._checkpoint = GenerationCheckpoint(
            completed_chapters=completed,
            outline_done=bool(project.outline),
            frontmatter_done=bool(project.frontmatter),
            backmatter_done=bool(project.backmatter),
            last_completed_step=(
                "backmatter" if project.backmatter
                else (f"chapter_{completed[-1]}" if completed else "")
            ),
        )

    def _checkpoint_path(self, project: BookProject) -> Optional[str]:
        if project.file_path:
            return str(Path(project.file_path).with_suffix(".checkpoint"))
        return None

    def _save_checkpoint(self, project: BookProject) -> None:
        """Persist the current checkpoint to disk."""
        if self._checkpoint is None:
            return
        cp_file = self._checkpoint_path(project)
        if not cp_file:
            return
        try:
            Path(cp_file).write_text(
                json.dumps(self._checkpoint.to_dict(), indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("Checkpoint save failed: %s", exc)

    def _mark_checkpoint_step(self, step: str, project: BookProject) -> None:
        """Record a completed step in the checkpoint and persist."""
        if self._checkpoint is None:
            self._checkpoint = GenerationCheckpoint()
        self._checkpoint.last_completed_step = step
        if step == "outline":
            self._checkpoint.outline_done = True
        elif step == "frontmatter":
            self._checkpoint.frontmatter_done = True
        elif step == "backmatter":
            self._checkpoint.backmatter_done = True
        elif step.startswith("chapter_"):
            idx = int(step.split("_")[1])
            if idx not in self._checkpoint.completed_chapters:
                self._checkpoint.completed_chapters.append(idx)
        self._save_checkpoint(project)

    # ------------------------------------------------------------------
    # Full pipeline  (with checkpoint-aware resume)
    # ------------------------------------------------------------------

    def generate_full_book(self) -> None:
        """Run the complete book generation pipeline.

        If a checkpoint exists, already-completed stages are skipped so
        generation can resume after an interruption.
        """
        if not self._project:
            self.error_occurred.emit("No project set.")
            return
        if not self._llm.is_loaded:
            self.error_occurred.emit("No model loaded.")
            return

        self._cancelled = False
        self._paused = False
        project = self._project
        self._target_words = project.generation_config.words_per_chapter
        self._base_temperature = 0.75

        total_steps = self._count_total_steps()
        completed_steps = self._count_completed_steps()

        try:
            # --- Step 1: Outline ---
            if not project.outline:
                self._fire_hooks("outline", "before", project=project)
                self._set_state(GenerationState.GENERATING_OUTLINE)
                self.log_message.emit("Generating book outline...")
                outline = self._generate_outline(project)
                project.outline = outline
                self.outline_generated.emit(outline)
                self._mark_checkpoint_step("outline", project)
                self.checkpoint_saved.emit(-1)
                completed_steps += 1
                self._update_progress(completed_steps, total_steps)
                self._fire_hooks("outline", "after", project=project, outline=outline)
                self._check_cancel()
            else:
                self.log_message.emit("Outline already exists — skipping.")
                completed_steps += 1
                self._update_progress(completed_steps, total_steps)

            # --- Step 2: Frontmatter ---
            if (project.generation_config.include_frontmatter
                    and not project.frontmatter):
                self._fire_hooks("frontmatter", "before", project=project)
                self._set_state(GenerationState.GENERATING_FRONTMATTER)
                self.log_message.emit("Generating front matter...")
                frontmatter = self._generate_frontmatter(project)
                project.frontmatter = frontmatter
                self.frontmatter_generated.emit(frontmatter)
                self._mark_checkpoint_step("frontmatter", project)
                completed_steps += 1
                self._update_progress(completed_steps, total_steps)
                self._fire_hooks("frontmatter", "after",
                                 project=project, frontmatter=frontmatter)
                self._check_cancel()
            elif project.frontmatter:
                completed_steps += 1
                self._update_progress(completed_steps, total_steps)

            # --- Step 3: Chapters ---
            chapters_to_gen = self._get_chapter_indices(project)
            for idx in chapters_to_gen:
                self._check_cancel()
                if self._paused:
                    self._set_state(GenerationState.PAUSED)
                    self.log_message.emit("Paused. Waiting for resume...")
                    while self._paused and not self._cancelled:
                        time.sleep(0.5)
                    if self._cancelled:
                        break
                    self._set_state(GenerationState.GENERATING_CHAPTER)

                chapter = project.get_chapter(idx)
                if not chapter:
                    continue

                # Skip already-generated chapters (checkpoint resume)
                if chapter.content_generated and idx in (
                    self._checkpoint.completed_chapters
                    if self._checkpoint else []
                ):
                    self.log_message.emit(
                        f"Skipping chapter {idx+1} (already generated)."
                    )
                    self._word_count_history.append(chapter.word_count)
                    completed_steps += 1
                    self._update_progress(completed_steps, total_steps)
                    continue

                # --- Generate chapter (with retries + quality gate) ---
                self._set_state(GenerationState.GENERATING_CHAPTER)
                project.current_chapter_index = idx
                self.chapter_started.emit(idx, chapter.title)
                self.log_message.emit(
                    f"Generating Chapter {idx+1}: {chapter.title}..."
                )

                content = self._generate_chapter_with_quality_gate(
                    project, chapter,
                )
                chapter.content_markdown = content
                chapter.content_generated = True
                chapter.word_count = len(content.split())
                self._word_count_history.append(chapter.word_count)

                # Save revision
                self._save_revision(chapter, content, "AI Generated")

                # Multi-pass refinement
                if project.generation_config.enable_refinement:
                    num_passes = project.generation_config.refinement_passes
                    for pass_num in range(1, num_passes + 1):
                        self._check_cancel()
                        self._fire_hooks("refine", "before",
                                         chapter=chapter, pass_num=pass_num)
                        self.refinement_pass.emit(pass_num, num_passes)
                        self.log_message.emit(
                            f"  Refinement pass {pass_num}/{num_passes}..."
                        )
                        refined = self._refine_chapter(
                            project, chapter, content, pass_num,
                        )
                        self._save_revision(chapter, refined, f"Refined v{pass_num}")
                        content = refined
                        chapter.content_markdown = content
                        chapter.word_count = len(content.split())
                        self._word_count_history[-1] = chapter.word_count
                        self._fire_hooks("refine", "after",
                                         chapter=chapter, pass_num=pass_num,
                                         content=refined)

                # Inter-chapter consistency check
                self._run_consistency_check(project, idx)

                self.chapter_completed.emit(idx)
                self._mark_checkpoint_step(f"chapter_{idx}", project)
                self.checkpoint_saved.emit(idx)
                completed_steps += 1
                self._update_progress(completed_steps, total_steps)
                self.log_message.emit(
                    f"Chapter {idx+1} complete ({chapter.word_count} words)."
                )

                # Generate summary (non-critical — don't block on failure)
                self._generate_and_store_summary(project, chapter)

                # Auto-save
                if project.generation_config.auto_save:
                    save_every = project.generation_config.save_interval
                    if (idx + 1) % save_every == 0 and project.file_path:
                        self.log_message.emit("Auto-saving project...")
                        self._auto_save_project(project)

            # --- Step 4: Backmatter ---
            if (project.generation_config.include_backmatter
                    and not project.backmatter):
                self._check_cancel()
                self._fire_hooks("backmatter", "before", project=project)
                self._set_state(GenerationState.GENERATING_BACKMATTER)
                self.log_message.emit("Generating back matter...")
                backmatter = self._generate_backmatter(project)
                project.backmatter = backmatter
                self.backmatter_generated.emit(backmatter)
                self._mark_checkpoint_step("backmatter", project)
                completed_steps += 1
                self._update_progress(completed_steps, total_steps)
                self._fire_hooks("backmatter", "after",
                                 project=project, backmatter=backmatter)

            self._set_state(GenerationState.COMPLETED)
            self.log_message.emit(
                f"Book generation complete! "
                f"{project.generated_count()}/{len(project.chapters)} chapters, "
                f"{project.total_words():,} total words."
            )
            if project.token_usage:
                self.log_message.emit(project.token_usage.summary_text())
            self.generation_finished.emit()

        except InterruptedError:
            self.log_message.emit(
                "Generation interrupted. Use 'Generate Full Book' again to "
                "resume from the last checkpoint."
            )
        except Exception as e:
            logger.exception("Generation error")
            self._set_state(GenerationState.ERROR)
            self.error_occurred.emit(str(e))
            self.log_message.emit(f"ERROR: {e}")

    # ==================================================================
    # Continue generation — append to an interrupted chapter
    # ==================================================================

    def continue_generation(self, chapter_index: int, min_additional_words: int = 500) -> None:
        """Continue generating an already-started chapter from where it stopped.

        Useful when generation was interrupted mid-chapter. The existing
        content is included as context and the model is instructed to
        continue seamlessly.
        """
        if not self._project or not self._llm.is_loaded:
            return

        project = self._project
        chapter = project.get_chapter(chapter_index)
        if not chapter:
            self.error_occurred.emit(f"Chapter {chapter_index+1} not found.")
            return

        existing = chapter.content_markdown or ""
        existing_words = len(existing.split())

        if existing_words >= self._target_words:
            self.log_message.emit(
                f"Chapter {chapter_index+1} already has {existing_words} words "
                f"(target: {self._target_words}). No continuation needed."
            )
            return

        words_needed = self._target_words - existing_words
        words_to_request = max(words_needed, min_additional_words)

        try:
            self._set_state(GenerationState.GENERATING_CHAPTER)
            self.chapter_started.emit(chapter_index, chapter.title)
            self.log_message.emit(
                f"Continuing Chapter {chapter_index+1}: {chapter.title} "
                f"({existing_words} words exist, need ~{words_to_request} more)..."
            )

            self._fire_hooks("chapter", "before",
                             project=project, chapter=chapter, mode="continue")

            # Build context for the chapter
            context = self._context_eng.build_context_for_chapter(
                chapter.index,
                reserved_generation_tokens=words_to_request // 3,
            )
            type_instructions = self._prompt_eng.get_chapter_type_instructions(
                project.ebook_type, chapter,
            )

            system = self._prompt_eng.build_system_prompt(
                project.ebook_type,
                extra_instructions=(
                    "You are CONTINUING an interrupted chapter. "
                    "Do NOT repeat what has already been written. "
                    "Pick up exactly where the existing text leaves off, "
                    "maintaining the same style, tone, and narrative voice. "
                    "Write smoothly from the last sentence without any "
                    "transition phrases like 'Continuing...' or 'The story "
                    "resumes...'. Begin directly with the next sentence."
                ),
            )

            # Truncate existing content to leave room for context
            max_existing_chars = min(len(existing), 6000)
            truncated_existing = existing[-max_existing_chars:]

            user = (
                f"Book: {project.metadata.title}\n"
                f"Chapter {chapter.index + 1}: {chapter.title}\n"
                f"Synopsis: {chapter.synopsis}\n\n"
            )
            if context.outline_excerpt:
                user += f"Outline:\n{context.outline_excerpt}\n\n"
            if context.previous_summary:
                user += f"Previous chapter summary:\n{context.previous_summary}\n\n"

            user += (
                f"--- EXISTING CHAPTER TEXT (do NOT repeat this) ---\n"
                f"{truncated_existing}\n"
                f"--- END OF EXISTING TEXT ---\n\n"
                f"Continue writing this chapter for approximately "
                f"{words_to_request} more words. Begin directly from where "
                f"the text above ends. Do not include any meta-commentary."
            )

            self._current_streamed_text = ""
            t0 = time.time()

            temp = self._compute_adaptive_temperature(chapter_index, project)
            result = self._llm.generate(
                system_prompt=system, user_prompt=user,
                temperature=temp, top_p=0.92, top_k=50,
                max_tokens=words_to_request + 1024,
                repeat_penalty=1.15,
                stream=True, on_token=self._on_stream_token,
            )
            self._track_tokens(
                f"continue_{chapter.index}", system, user, result,
                time.time() - t0,
            )

            # Append the continuation
            new_content = existing + "\n" + result.strip()
            chapter.content_markdown = new_content
            chapter.content_generated = True
            chapter.word_count = len(new_content.split())
            self._save_revision(chapter, new_content, "Continued")

            self._fire_hooks("chapter", "after",
                             project=project, chapter=chapter, mode="continue")

            # Re-generate summary since chapter changed
            self._generate_and_store_summary(project, chapter)

            self.chapter_completed.emit(chapter_index)
            self.single_chapter_done.emit(chapter_index)
            self._mark_checkpoint_step(f"chapter_{chapter_index}", project)
            self.log_message.emit(
                f"Chapter {chapter_index+1} continued to "
                f"{chapter.word_count} words."
            )
            self._set_state(GenerationState.COMPLETED)

        except Exception as e:
            self._set_state(GenerationState.ERROR)
            self.error_occurred.emit(str(e))

    # ==================================================================
    # Single chapter regeneration (called from editor)
    # ==================================================================

    def regenerate_single_chapter(self, chapter_index: int) -> None:
        """Regenerate a single chapter. Runs in calling thread (use QThread)."""
        if not self._project or not self._llm.is_loaded:
            return
        project = self._project
        chapter = project.get_chapter(chapter_index)
        if not chapter:
            self.error_occurred.emit(f"Chapter {chapter_index+1} not found.")
            return

        try:
            self._set_state(GenerationState.GENERATING_CHAPTER)
            self._fire_hooks("chapter", "before",
                             project=project, chapter=chapter, mode="regenerate")
            self.chapter_started.emit(chapter_index, chapter.title)
            self.log_message.emit(f"Regenerating Chapter {chapter_index+1}...")

            content = self._generate_chapter_with_quality_gate(project, chapter)
            chapter.content_markdown = content
            chapter.content_generated = True
            chapter.word_count = len(content.split())
            if chapter_index < len(self._word_count_history):
                self._word_count_history[chapter_index] = chapter.word_count
            else:
                self._word_count_history.append(chapter.word_count)
            self._save_revision(chapter, content, "Regenerated")

            self._generate_and_store_summary(project, chapter)
            self._fire_hooks("chapter", "after",
                             project=project, chapter=chapter, mode="regenerate")
            self.chapter_completed.emit(chapter_index)
            self.single_chapter_done.emit(chapter_index)
            self.log_message.emit(
                f"Chapter {chapter_index+1} regenerated ({chapter.word_count} words)."
            )
            self._set_state(GenerationState.COMPLETED)
        except Exception as e:
            self._set_state(GenerationState.ERROR)
            self.error_occurred.emit(str(e))

    # ==================================================================
    # Multi-pass refinement
    # ==================================================================

    def refine_single_chapter(self, chapter_index: int) -> None:
        """Refine an already-generated chapter."""
        if not self._project or not self._llm.is_loaded:
            return
        project = self._project
        chapter = project.get_chapter(chapter_index)
        if not chapter or not chapter.content_generated:
            self.error_occurred.emit("Chapter not generated yet.")
            return

        try:
            self._set_state(GenerationState.POST_PROCESSING)
            self._fire_hooks("refine", "before",
                             chapter=chapter, pass_num=1)
            self.log_message.emit(f"Refining Chapter {chapter_index+1}...")

            refined = self._refine_chapter(
                project, chapter, chapter.content_markdown, 1,
            )
            self._save_revision(chapter, refined, "Refined")
            chapter.content_markdown = refined
            chapter.word_count = len(refined.split())
            if chapter_index < len(self._word_count_history):
                self._word_count_history[chapter_index] = chapter.word_count
            self._fire_hooks("refine", "after",
                             chapter=chapter, pass_num=1, content=refined)
            self.chapter_completed.emit(chapter_index)
            self.single_chapter_done.emit(chapter_index)
            self.log_message.emit(f"Chapter {chapter_index+1} refined.")
            self._set_state(GenerationState.COMPLETED)
        except Exception as e:
            self._set_state(GenerationState.ERROR)
            self.error_occurred.emit(str(e))

    # ==================================================================
    # Generation with retry + quality gate
    # ==================================================================

    def _generate_chapter_with_retry(
        self, project: BookProject, chapter: Chapter,
    ) -> str:
        """Generate a chapter with retry logic (legacy, used internally)."""
        max_retries = project.generation_config.max_retries
        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                return self._generate_chapter(project, chapter)
            except Exception as e:
                last_error = e
                logger.warning("Chapter generation attempt %d failed: %s", attempt, e)
                if attempt < max_retries:
                    self.log_message.emit(
                        f"  Retry {attempt}/{max_retries}..."
                    )
                    time.sleep(1)
        raise last_error  # type: ignore

    def _generate_chapter_with_quality_gate(
        self, project: BookProject, chapter: Chapter,
    ) -> str:
        """Generate a chapter, validate with quality gate, and retry if needed.

        Combines retry logic (for errors) with quality validation (for
        substandard output).  Up to ``max_retries + 1`` total attempts
        are made; if the final attempt still fails the quality gate the
        best-scoring text is returned with a warning.
        """
        max_retries = project.generation_config.max_retries
        best_content = ""
        best_score = -1.0
        last_error: Optional[Exception] = None

        for attempt in range(1, max_retries + 2):
            try:
                content = self._generate_chapter(project, chapter)
            except Exception as e:
                last_error = e
                logger.warning(
                    "Chapter gen attempt %d error: %s", attempt, e,
                )
                if attempt <= max_retries:
                    self.log_message.emit(
                        f"  Retry {attempt}/{max_retries} (error)..."
                    )
                    time.sleep(1)
                continue

            # Run quality gate
            report = self._run_quality_gate(
                content, project.generation_config.words_per_chapter,
            )
            self.quality_report.emit(report)
            self._fire_hooks("quality_gate", "after",
                             chapter=chapter, report=report, attempt=attempt)

            if report.score > best_score:
                best_score = report.score
                best_content = content

            if report.passed:
                if attempt > 1:
                    self.log_message.emit(
                        f"  Quality gate passed on attempt {attempt}."
                    )
                return content

            # Quality gate failed — log why and retry
            self.log_message.emit(
                f"  Quality gate issue (attempt {attempt}): "
                f"{', '.join(report.issues[:3])}"
            )
            if attempt <= max_retries:
                self.log_message.emit(
                    f"  Retrying with adjusted parameters..."
                )
                time.sleep(0.5)

        # All attempts exhausted — return best content even if imperfect
        if best_content:
            self.log_message.emit(
                f"  Warning: quality gate not fully passed. "
                f"Best score: {best_score:.2f}. Using best attempt."
            )
            return best_content

        # All attempts errored out
        if last_error:
            raise last_error
        return ""

    # ==================================================================
    # Quality Gate
    # ==================================================================

    def _run_quality_gate(
        self, content: str, target_words: int,
    ) -> QualityReport:
        """Validate generated content for minimum quality standards.

        Checks:
        1. **Word count** — must be >= 40% of target to pass.
        2. **Repetition** — n-gram overlap score must be below threshold.
        3. **Structural** — content should have paragraph breaks and
           not be a single block of text.
        """
        words = content.split()
        word_count = len(words)
        issues: list[str] = []
        score = 1.0

        # --- Word count check ---
        if word_count < target_words * 0.4:
            issues.append(
                f"Word count ({word_count}) is below 40% of target ({target_words})."
            )
            score -= 0.4
        elif word_count < target_words * 0.7:
            issues.append(
                f"Word count ({word_count}) is below 70% of target ({target_words})."
            )
            score -= 0.15

        # --- Repetition detection (3-gram and 4-gram) ---
        rep_score = self._compute_repetition_score(words)
        if rep_score > 0.25:
            issues.append(f"High repetition detected (score: {rep_score:.2f}).")
            score -= 0.3
        elif rep_score > 0.15:
            issues.append(f"Moderate repetition (score: {rep_score:.2f}).")
            score -= 0.1

        # --- Structural check ---
        paragraph_count = content.count("\n\n") + 1
        if paragraph_count < 2 and word_count > 300:
            issues.append("Content lacks paragraph breaks (single block).")
            score -= 0.1

        # --- Very short content check ---
        if word_count < 50:
            issues.append("Content is extremely short (< 50 words).")
            score -= 0.5

        score = max(0.0, min(1.0, score))
        return QualityReport(
            passed=score >= 0.5 and word_count >= target_words * 0.4,
            word_count=word_count,
            target_words=target_words,
            repetition_score=rep_score,
            issues=issues,
            score=score,
        )

    @staticmethod
    def _compute_repetition_score(words: list[str], n: int = 3) -> float:
        """Compute n-gram repetition ratio.

        Returns a float between 0.0 (no repetition) and 1.0 (highly
        repetitive).  Uses the ratio of repeated n-grams to total
        unique n-grams as the score.
        """
        if len(words) < n * 2:
            return 0.0
        ngrams: list[str] = []
        for i in range(len(words) - n + 1):
            ngrams.append(" ".join(words[i:i + n]))

        counts = Counter(ngrams)
        repeated = sum(c for c in counts.values() if c > 1)
        total_unique = len(counts)
        if total_unique == 0:
            return 0.0
        return repeated / total_unique

    # ==================================================================
    # Adaptive Temperature
    # ==================================================================

    def _compute_adaptive_temperature(
        self, chapter_index: int, project: BookProject,
    ) -> float:
        """Compute temperature that adapts to generation history.

        Strategy:
        - If previous chapters were significantly under the target word
          count, increase temperature slightly to encourage more expansive
          writing.
        - If previous chapters were over the target, decrease temperature
          for more focused output.
        - First and last chapters get a slight bump for stronger hooks
          and conclusions.
        - The adjustment is bounded to prevent extreme values.
        """
        base = self._base_temperature
        target = self._target_words
        total_chapters = len(project.chapters)

        # Position-based adjustment
        position_adj = 0.0
        if chapter_index == 0:
            position_adj = 0.03  # Slightly hotter for opening hook
        elif chapter_index == total_chapters - 1 and total_chapters > 1:
            position_adj = 0.02  # Slightly hotter for conclusion

        # History-based adjustment
        history_adj = 0.0
        if self._word_count_history:
            recent = self._word_count_history[-3:]  # last 3 chapters
            avg_recent = sum(recent) / len(recent)
            ratio = avg_recent / target if target > 0 else 1.0

            if ratio < 0.6:
                history_adj = 0.08  # Significantly under target — more creative
            elif ratio < 0.8:
                history_adj = 0.04  # Somewhat under
            elif ratio > 1.3:
                history_adj = -0.05  # Over target — more focused
            elif ratio > 1.1:
                history_adj = -0.02  # Slightly over

        # Genre-based baseline adjustment
        genre_adj = 0.0
        if project.ebook_type in (
            EbookType.POETRY_COLLECTION, EbookType.CHILDREN_BOOK,
        ):
            genre_adj = -0.05  # More controlled for poetry/children's
        elif project.ebook_type in (
            EbookType.SCIFI_FANTASY, EbookType.MYSTERY_THRILLER,
            EbookType.HISTORICAL_FICTION,
        ):
            genre_adj = 0.02  # Slightly more creative for genre fiction

        temp = base + position_adj + history_adj + genre_adj
        return max(0.3, min(1.2, temp))  # Hard bounds

    # ==================================================================
    # Dynamic Context Budget
    # ==================================================================

    def _compute_reserved_tokens(
        self, chapter_index: int, project: BookProject,
    ) -> int:
        """Dynamically compute reserved generation tokens.

        Later chapters tend to need more context (summaries accumulate),
        so the generation budget is scaled accordingly.  If the model
        has a large context window, more tokens are reserved for output.
        """
        base_reserve = project.generation_config.words_per_chapter // 3
        model_ctx = self._llm.context_size if self._llm.is_loaded else 8192

        # Scale generation reserve as a fraction of model context
        # Early chapters: reserve up to 50% for generation
        # Late chapters:  reserve ~35% (more context needed)
        total_chapters = max(len(project.chapters), 1)
        position_ratio = chapter_index / total_chapters
        gen_fraction = 0.50 - (position_ratio * 0.15)  # 0.50 → 0.35

        dynamic_reserve = int(model_ctx * gen_fraction)

        # Use the larger of the base and dynamic reserve, but cap
        # at 60% of the model context to leave room for system prompt
        max_reserve = int(model_ctx * 0.60)
        return min(max(base_reserve, dynamic_reserve), max_reserve)

    # ==================================================================
    # Chain-of-Thought Planning
    # ==================================================================

    def _generate_chapter_plan(
        self, project: BookProject, chapter: Chapter,
    ) -> str:
        """Ask the LLM to produce a brief writing plan for the chapter.

        This is injected as context before the actual generation,
        improving structure and coherence for complex chapters.
        Returns the plan text, or empty string if planning is disabled
        or the chapter type doesn't benefit from it.
        """
        # Only use CoT for types that benefit from structured planning
        planning_types = {
            EbookType.FICTION_NOVEL, EbookType.SCIFI_FANTASY,
            EbookType.MYSTERY_THRILLER, EbookType.HISTORICAL_FICTION,
            EbookType.TECHNICAL_BOOK, EbookType.TEXTBOOK,
            EbookType.NON_FICTION_GUIDE,
        }
        if project.ebook_type not in planning_types:
            return ""

        # Skip planning for very short chapter targets
        if project.generation_config.words_per_chapter < 1200:
            return ""

        system = (
            "You are a story/section planner. Given the book context and "
            "chapter synopsis, produce a BRIEF writing plan (150-300 words) "
            "covering:\n"
            "1. Opening hook or transition from previous chapter\n"
            "2. Key scenes or points to cover (3-5 items)\n"
            "3. Emotional arc or rhetorical flow\n"
            "4. Closing beat or cliffhanger\n\n"
            "Be concise — this plan guides the actual writing, not replaces it."
        )

        user = (
            f"Book: {project.metadata.title}\n"
            f"Type: {EBOOK_TYPE_LABELS.get(project.ebook_type, 'Book')}\n"
            f"Chapter {chapter.index + 1}: {chapter.title}\n"
            f"Synopsis: {chapter.synopsis}\n"
        )
        if chapter.index > 0 and self._word_count_history:
            user += (
                f"Previous chapter was ~{self._word_count_history[-1]} words.\n"
            )

        try:
            self.log_message.emit("  Planning chapter structure...")
            self._current_streamed_text = ""
            t0 = time.time()
            plan = self._llm.generate(
                system_prompt=system, user_prompt=user,
                temperature=0.4, max_tokens=400,
                stream=False,
            )
            self._track_tokens(
                f"plan_{chapter.index}", system, user, plan,
                time.time() - t0,
            )
            return plan.strip()
        except Exception as exc:
            logger.warning("Chapter planning failed: %s", exc)
            return ""

    # ==================================================================
    # Inter-Chapter Consistency Check
    # ==================================================================

    def _run_consistency_check(
        self, project: BookProject, chapter_index: int,
    ) -> None:
        """Lightweight consistency check between adjacent chapters.

        Compares the just-generated chapter with the previous one for
        obvious inconsistencies (character name mismatches, timeline
        contradictions).  Runs a fast LLM call and emits the result.
        """
        if chapter_index == 0:
            return  # No previous chapter to compare against

        prev = project.get_chapter(chapter_index - 1)
        curr = project.get_chapter(chapter_index)
        if not prev or not curr or not prev.content_generated:
            return

        # Truncate to keep the check fast and cheap
        prev_text = (prev.content_markdown or "")[:2000]
        curr_text = (curr.content_markdown or "")[:2000]

        system = (
            "You are a continuity editor. Briefly check these two "
            "adjacent book chapters for glaring inconsistencies. "
            "Focus ONLY on:\n"
            "- Character name spelling changes\n"
            "- Contradictory events or facts\n"
            "- Timeline impossibilities\n\n"
            "If everything looks consistent, reply with: "
            "'No issues found.'\n"
            "If issues exist, list each on one line starting with '- '.\n"
            "Be very brief (under 100 words total)."
        )
        user = (
            f"PREVIOUS CHAPTER ({prev.title}):\n{prev_text}\n\n"
            f"CURRENT CHAPTER ({curr.title}):\n{curr_text}"
        )

        try:
            self._current_streamed_text = ""
            t0 = time.time()
            result = self._llm.generate(
                system_prompt=system, user_prompt=user,
                temperature=0.2, max_tokens=150,
                stream=False,
            )
            self._track_tokens(
                f"consistency_{chapter_index}", system, user,
                result, time.time() - t0,
            )
            report = result.strip()
            self.consistency_check.emit(chapter_index, report)

            if "no issues found" not in report.lower():
                self.log_message.emit(
                    f"  Consistency note for Ch.{chapter_index+1}: {report[:200]}"
                )
        except Exception as exc:
            logger.debug("Consistency check skipped: %s", exc)

    # ==================================================================
    # Individual generation steps
    # ==================================================================

    def _generate_outline(self, project: BookProject) -> str:
        system, user = self._prompt_eng.build_outline_prompt(project)
        self._current_streamed_text = ""
        t0 = time.time()
        result = self._llm.generate(
            system_prompt=system, user_prompt=user,
            temperature=0.6, top_p=0.9, max_tokens=4096,
            repeat_penalty=1.1, stream=True,
            on_token=self._on_stream_token,
        )
        self._track_tokens("outline", system, user, result, time.time() - t0)
        return result.strip()

    def _generate_frontmatter(self, project: BookProject) -> str:
        system, user = self._prompt_eng.build_frontmatter_prompt(project)
        self._current_streamed_text = ""
        t0 = time.time()
        result = self._llm.generate(
            system_prompt=system, user_prompt=user,
            temperature=0.7, max_tokens=3000,
            stream=True, on_token=self._on_stream_token,
        )
        self._track_tokens("frontmatter", system, user, result, time.time() - t0)
        return result.strip()

    def _generate_backmatter(self, project: BookProject) -> str:
        system, user = self._prompt_eng.build_backmatter_prompt(project)
        self._current_streamed_text = ""
        t0 = time.time()
        result = self._llm.generate(
            system_prompt=system, user_prompt=user,
            temperature=0.7, max_tokens=3000,
            stream=True, on_token=self._on_stream_token,
        )
        self._track_tokens("backmatter", system, user, result, time.time() - t0)
        return result.strip()

    def _generate_chapter(self, project: BookProject, chapter: Chapter) -> str:
        """Generate a single chapter with all context engineering.

        Enhanced with:
        - Dynamic context budget allocation
        - Adaptive temperature
        - Optional chain-of-thought planning
        """
        # Dynamic context budget
        reserved_tokens = self._compute_reserved_tokens(chapter.index, project)

        context = self._context_eng.build_context_for_chapter(
            chapter.index,
            reserved_generation_tokens=reserved_tokens,
        )

        type_instructions = self._prompt_eng.get_chapter_type_instructions(
            project.ebook_type, chapter,
        )

        # Chain-of-thought planning for complex chapters
        plan_text = self._generate_chapter_plan(project, chapter)

        system, user = self._prompt_eng.build_chapter_prompt(
            project=project, chapter=chapter,
            previous_chapter_summary=context.previous_summary,
            outline_context=context.outline_excerpt,
            chapter_specific_instructions=type_instructions,
        )

        # Inject writing plan if available
        if plan_text:
            user = (
                f"## Chapter Writing Plan\n{plan_text}\n\n"
                f"Follow this plan as you write the chapter below.\n\n"
                f"---\n\n{user}"
            )

        # Inject world bible if enabled
        if (project.generation_config.inject_world_bible
                and project.world_bible is not None):
            wb_text = project.world_bible.to_context_text(chapter.index)
            if wb_text:
                user = f"{wb_text}\n\n---\n\n{user}"

        # Inject sliding window text
        if context.sliding_window_text:
            user = (
                f"{context.sliding_window_text}\n\n"
                f"--- END OF PREVIOUS CONTENT ---\n\n"
                f"{user}"
            )

        stop = project.generation_config.custom_stop_sequences or None

        # Adaptive temperature
        temp = self._compute_adaptive_temperature(chapter.index, project)

        self._current_streamed_text = ""
        t0 = time.time()
        result = self._llm.generate(
            system_prompt=system, user_prompt=user,
            temperature=temp, top_p=0.92, top_k=50,
            max_tokens=project.generation_config.words_per_chapter + 1024,
            repeat_penalty=1.12, stop=stop,
            stream=True, on_token=self._on_stream_token,
        )
        self._track_tokens(
            f"chapter_{chapter.index}", system, user, result,
            time.time() - t0,
        )
        return result.strip()

    def _refine_chapter(
        self, project: BookProject, chapter: Chapter,
        current_content: str, pass_num: int,
    ) -> str:
        """Refine an existing chapter draft."""
        system = self._prompt_eng.build_system_prompt(
            project.ebook_type,
            extra_instructions=(
                "You are now in REFINEMENT MODE. Improve the following chapter "
                "draft for quality, consistency, and style. Do NOT change the "
                "plot or add new major events. Focus on: prose quality, dialogue "
                "naturalness, sensory details, pacing, and eliminating "
                "repetitions or cliches. Return the complete refined chapter."
            ),
        )

        # For later passes, include quality feedback if available
        quality_note = ""
        if pass_num > 1 and current_content:
            report = self._run_quality_gate(
                current_content,
                project.generation_config.words_per_chapter,
            )
            if report.issues:
                quality_note = (
                    f"\n\nQuality issues to address:\n"
                    + "\n".join(f"- {issue}" for issue in report.issues)
                )

        # Use smart truncation: keep the beginning (for style reference)
        # and end (for continuation) of the draft
        draft = current_content
        if len(draft) > 8000:
            half = 4000
            draft = (
                draft[:half]
                + f"\n\n[... {len(draft) - 2 * half} characters omitted for context "
                f"window ...]\n\n"
                + draft[-half:]
            )

        user = (
            f"Refine the following chapter draft of \"{project.metadata.title}\":\n\n"
            f"Chapter {chapter.index + 1}: {chapter.title}\n"
            f"Synopsis: {chapter.synopsis}\n"
            f"{quality_note}\n\n"
            f"--- DRAFT ---\n{draft}\n--- END DRAFT ---\n\n"
            f"Write the complete refined chapter:"
        )
        self._current_streamed_text = ""
        t0 = time.time()
        result = self._llm.generate(
            system_prompt=system, user_prompt=user,
            temperature=project.generation_config.refinement_temperature,
            top_p=0.9, top_k=40,
            max_tokens=project.generation_config.words_per_chapter + 1024,
            repeat_penalty=1.15, stream=True,
            on_token=self._on_stream_token,
        )
        self._track_tokens(
            f"refine_{chapter.index}_v{pass_num}", system, user,
            result, time.time() - t0,
        )
        return result.strip()

    def _generate_and_store_summary(
        self, project: BookProject, chapter: Chapter,
    ) -> str:
        """Generate a concise summary of a chapter for context engineering.

        Runs non-critically — failures are logged but do not halt the
        pipeline.  The summary is stored both in the ContextEngineer
        and on the chapter's generation_notes field.
        """
        try:
            system, user = self._prompt_eng.build_summary_prompt(
                chapter, project.metadata.title,
            )
            self._fire_hooks("summary", "before", chapter=chapter)
            self._current_streamed_text = ""
            t0 = time.time()
            summary = self._llm.generate(
                system_prompt=system, user_prompt=user,
                temperature=0.3, max_tokens=300,
                stream=False,
            )
            self._track_tokens(
                f"summary_{chapter.index}", system, user,
                summary, time.time() - t0,
            )
            summary = summary.strip()
            self._context_eng.store_summary(chapter.index, summary)
            self._fire_hooks("summary", "after",
                             chapter=chapter, summary=summary)
            self.log_message.emit(f"  Summary stored for Chapter {chapter.index+1}.")
            return summary
        except Exception as e:
            logger.warning(
                "Failed to generate summary for chapter %d: %s",
                chapter.index, e,
            )
            # Fallback: generate a simple extractive summary
            fallback = self._extractive_fallback_summary(chapter)
            if fallback:
                self._context_eng.store_summary(chapter.index, fallback)
            return fallback

    def _extractive_fallback_summary(self, chapter: Chapter) -> str:
        """Create a basic summary from the first and last sentences when
        LLM summary generation fails."""
        text = chapter.content_markdown or ""
        if not text:
            return ""
        sentences = re.split(r'(?<=[.!?])\s+', text)
        if len(sentences) <= 3:
            return text[:300]
        # Take first 2 sentences and last sentence
        selected = sentences[:2] + [sentences[-1]]
        return " ".join(selected)

    # ==================================================================
    # Import markdown chapters
    # ==================================================================

    def import_markdown_file(
        self, file_path: str, project: BookProject,
    ) -> int:
        """Import a markdown file as one or more chapters.

        Splits on '## Chapter' or '## ' headings. Returns number of
        chapters added.
        """
        text = Path(file_path).read_text(encoding="utf-8")
        parts = re.split(r"(?=^##\s+Chapter\s+\d)", text, flags=re.MULTILINE)

        if len(parts) <= 1:
            parts = [text]

        count = 0
        for part in parts:
            part = part.strip()
            if not part:
                continue
            title_match = re.match(r"^##\s+(.+)$", part, re.MULTILINE)
            title = (
                title_match.group(1).strip() if title_match
                else f"Imported {count+1}"
            )
            if title_match:
                content = re.sub(
                    r"^##\s+.+\n?", "", part, count=1,
                ).strip()
            else:
                content = part

            ch = project.add_chapter(title=title)
            ch.content_markdown = content
            ch.content_generated = True
            ch.word_count = len(content.split())
            count += 1

        self.log_message.emit(f"Imported {count} chapters from {file_path}")
        return count

    # ==================================================================
    # AI world bible generation
    # ==================================================================

    def generate_world_bible(
        self, description: str, project: BookProject,
    ) -> str:
        """Ask the LLM to generate world bible entries from a description."""
        system = (
            "You are a world-building expert. Given a book description, "
            "generate a structured list of key characters, locations, and "
            "concepts. Format each entry as:\n"
            "TYPE: Character|Location|Concept|Item|Organization\n"
            "NAME: <name>\n"
            "DESCRIPTION: <1-2 sentence description>\n"
            "ALIASES: comma,separated,aliases\n"
            "ATTRIBUTES: key1=value1, key2=value2\n\n"
            "Generate 8-15 entries covering the main characters, key "
            "locations, and important concepts. Separate entries with "
            "'---'."
        )
        self._current_streamed_text = ""
        result = self._llm.generate(
            system_prompt=system,
            user_prompt=(
                f"Book: {project.metadata.title}\n"
                f"Type: {EBOOK_TYPE_LABELS.get(project.ebook_type, 'Book')}\n\n"
                f"Description:\n{description}"
            ),
            temperature=0.6, max_tokens=4096,
            stream=True, on_token=self._on_stream_token,
        )
        return result.strip()

    # ==================================================================
    # Helpers
    # ==================================================================

    def _on_stream_token(self, token: str) -> None:
        self._current_streamed_text += token
        self.chapter_progress.emit(token)

    def _set_state(self, state: GenerationState) -> None:
        if self._project:
            self._project.state = state
        self.state_changed.emit(state.value)

    def _update_progress(self, completed: int, total: int) -> None:
        pct = (completed / total * 100) if total > 0 else 0
        if self._project:
            self._project.progress_pct = pct
        self.progress_changed.emit(pct)

    def _check_cancel(self) -> None:
        if self._cancelled:
            self._set_state(GenerationState.CANCELLED)
            raise InterruptedError("Generation cancelled.")

    def _get_chapter_indices(self, project: BookProject) -> list[int]:
        config = project.generation_config
        if config.chapters_to_generate:
            return [i for i in config.chapters_to_generate
                    if i < len(project.chapters)]
        return list(range(len(project.chapters)))

    def _count_total_steps(self) -> int:
        if not self._project:
            return 1
        p = self._project
        steps = 0
        if not p.outline:
            steps += 1
        if p.generation_config.include_frontmatter and not p.frontmatter:
            steps += 1
        steps += len(self._get_chapter_indices(p))
        if p.generation_config.include_backmatter and not p.backmatter:
            steps += 1
        return max(steps, 1)

    def _count_completed_steps(self) -> int:
        """Count steps already completed (for checkpoint-aware progress)."""
        if not self._project:
            return 0
        p = self._project
        steps = 0
        if p.outline:
            steps += 1
        if p.generation_config.include_frontmatter and p.frontmatter:
            steps += 1
        if p.generation_config.include_backmatter and p.backmatter:
            steps += 1
        # Already-generated chapters
        for idx in self._get_chapter_indices(p):
            ch = p.get_chapter(idx)
            if ch and ch.content_generated:
                steps += 1
        return steps

    def _auto_save_project(self, project: BookProject) -> None:
        if not project.file_path:
            return
        try:
            data = project.to_dict()
            with open(project.file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning("Auto-save failed: %s", e)

    def _save_revision(
        self, chapter: Chapter, content: str, label: str,
    ) -> None:
        if self._project and self._project.revision_history is not None:
            self._project.revision_history.add_revision(
                chapter.id, chapter.index, content, label,
            )

    def _track_tokens(
        self, stage: str, system: str, user: str,
        completion: str, duration: float,
    ) -> None:
        """Record token usage for a generation call."""
        if self._project and self._project.token_usage is not None:
            prompt_tokens = self._llm.count_tokens(system + user)
            completion_tokens = self._llm.count_tokens(completion)
            self._project.token_usage.record(
                stage, prompt_tokens, completion_tokens, duration,
            )


# ======================================================================
# Worker threads
# ======================================================================

from PySide6.QtCore import QThread


class GenerationWorker(QThread):
    """Worker thread for full-book generation pipeline."""

    finished_signal = Signal()
    error_signal = Signal(str)

    def __init__(
        self, harness: AIHarness, parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._harness = harness

    def run(self) -> None:
        try:
            self._harness.generate_full_book()
        except InterruptedError:
            pass
        except Exception as e:
            self.error_signal.emit(str(e))
        finally:
            self.finished_signal.emit()


class SingleChapterWorker(QThread):
    """Worker for regenerating, refining, or continuing a single chapter."""

    finished_signal = Signal()
    error_signal = Signal(str)

    def __init__(
        self,
        harness: AIHarness,
        chapter_index: int,
        mode: str = "regenerate",
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._harness = harness
        self._chapter_index = chapter_index
        self._mode = mode  # "regenerate", "refine", or "continue"

    def run(self) -> None:
        try:
            if self._mode == "regenerate":
                self._harness.regenerate_single_chapter(self._chapter_index)
            elif self._mode == "refine":
                self._harness.refine_single_chapter(self._chapter_index)
            elif self._mode == "continue":
                self._harness.continue_generation(self._chapter_index)
        except InterruptedError:
            pass
        except Exception as e:
            self.error_signal.emit(str(e))
        finally:
            self.finished_signal.emit()