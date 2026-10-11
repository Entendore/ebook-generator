"""Generation panel — controls and monitors the book generation process."""



from __future__ import annotations



import time

from typing import Optional



from PySide6.QtCore import Qt, QTimer

from PySide6.QtWidgets import (

    QDialog,

    QHBoxLayout,

    QLabel,

    QListWidget,

    QListWidgetItem,

    QPushButton,

    QProgressBar,

    QTextEdit,

    QVBoxLayout,

    QWidget,

)



from ..ai.harness import AIHarness, GenerationWorker

from ..models.book_project import BookProject, GenerationState, EbookType, EBOOK_TYPE_LABELS



# ---------------------------------------------------------------------------

# Catppuccin Mocha dark palette

# ---------------------------------------------------------------------------

CATPPUCCIN_BG = "#1e1e2e"

CATPPUCCIN_TEXT = "#cdd6f4"

CATPPUCCIN_ACCENT = "#89b4fa"

CATPPUCCIN_BORDER = "#313244"

CATPPUCCIN_SURFACE = "#181825"

CATPPUCCIN_GREEN = "#27ae60"

CATPPUCCIN_RED = "#e74c3c"

CATPPUCCIN_SUBTEXT = "#a6adc8"



_DARK_GROUPBOX = f"""

QGroupBox {{

    color: {CATPPUCCIN_TEXT};

    border: 1px solid {CATPPUCCIN_BORDER};

    border-radius: 6px;

    margin-top: 12px;

    padding-top: 14px;

    font-weight: bold;

    background: {CATPPUCCIN_SURFACE};

}}

QGroupBox::title {{

    subcontrol-origin: margin;

    left: 10px;

    padding: 0 4px;

}}

"""



_DARK_BUTTON = f"""

QPushButton {{

    background: {CATPPUCCIN_BORDER};

    color: {CATPPUCCIN_TEXT};

    border: 1px solid {CATPPUCCIN_BORDER};

    border-radius: 4px;

    padding: 6px 14px;

    font-size: 13px;

}}

QPushButton:hover {{

    background: {CATPPUCCIN_ACCENT};

    color: {CATPPUCCIN_BG};

}}

QPushButton:disabled {{

    background: {CATPPUCCIN_SURFACE};

    color: {CATPPUCCIN_BORDER};

}}

"""



_GREEN_BUTTON = f"""

QPushButton {{

    background: {CATPPUCCIN_GREEN};

    color: #ffffff;

    border: none;

    border-radius: 4px;

    padding: 10px 20px;

    font-size: 15px;

    font-weight: bold;

}}

QPushButton:hover {{

    background: #2ecc71;

}}

QPushButton:disabled {{

    background: {CATPPUCCIN_SURFACE};

    color: {CATPPUCCIN_BORDER};

}}

"""



_ACCENT_BUTTON = f"""

QPushButton {{

    background: {CATPPUCCIN_BLUE};

    color: {CATPPUCCIN_BG};

    border: none;

    border-radius: 4px;

    padding: 6px 14px;

    font-size: 12px;

    font-weight: bold;

}}

QPushButton:hover {{

    background: #b4befe;

}}

QPushButton:disabled {{

    background: {CATPPUCCIN_SURFACE};

    color: {CATPPUCCIN_BORDER};

}}

"""



_RED_BUTTON = f"""

QPushButton {{

    background: {CATPPUCCIN_RED};

    color: #ffffff;

    border: none;

    border-radius: 4px;

    padding: 6px 14px;

    font-size: 13px;

}}

QPushButton:hover {{

    background: #c0392b;

}}

QPushButton:disabled {{

    background: {CATPPUCCIN_SURFACE};

    color: {CATPPUCCIN_BORDER};

}}

"""



_PROGRESS_BAR = f"""

QProgressBar {{

    border: 1px solid {CATPPUCCIN_BORDER};

    border-radius: 4px;

    background: {CATPPUCCIN_SURFACE};

    text-align: center;

    color: {CATPPUCCIN_TEXT};

    height: 22px;

    font-size: 12px;

}}

QProgressBar::chunk {{

    background: {CATPPUCCIN_ACCENT};

    border-radius: 3px;

}}

"""



_LIST_WIDGET = f"""

QListWidget {{

    background: {CATPPUCCIN_SURFACE};

    color: {CATPPUCCIN_TEXT};

    border: 1px solid {CATPPUCCIN_BORDER};

    border-radius: 4px;

    padding: 2px;

    font-size: 13px;

}}

QListWidget::item {{

    padding: 4px 2px;

}}

QListWidget::item:hover {{

    background: {CATPPUCCIN_BORDER};

}}

"""



_LOG_EDIT = f"""

QTextEdit {{

    background: {CATPPUCCIN_SURFACE};

    color: {CATPPUCCIN_TEXT};

    border: 1px solid {CATPPUCCIN_BORDER};

    border-radius: 4px;

    font-family: "Fira Code", "JetBrains Mono", "Consolas", monospace;

    font-size: 12px;

    padding: 4px;

}}

"""



_LABEL_STYLE = f"color: {CATPPUCCIN_TEXT}; font-size: 13px;"

_SUB_LABEL_STYLE = f"color: {CATPPUCCIN_SUBTEXT}; font-size: 12px;"





class GenerationPanel(QWidget):

    """Panel for controlling and monitoring the ebook generation process."""



    def __init__(self, project: BookProject, harness: AIHarness, parent: Optional[QWidget] = None) -> None:

        super().__init__(parent)



        self._project = project

        self._harness = harness

        self._worker: Optional[GenerationWorker] = None



        # Elapsed-time tracking

        self._elapsed_seconds: int = 0

        self._timer = QTimer(self)

        self._timer.setInterval(1000)

        self._timer.timeout.connect(self._tick_elapsed)



        self._build_ui()

        self._connect_harness_signals()

        self._update_button_states()



    # ------------------------------------------------------------------

    # Public API

    # ------------------------------------------------------------------



    def set_project(self, project: BookProject) -> None:

        """Switch to a different *project* while keeping the same harness."""

        self._project = project

        self._harness.set_project(project)

        self.refresh()



    def refresh(self) -> None:

        """Re-sync the UI with the current project state."""

        self._rebuild_chapter_list()

        self._update_context_info()

        self._update_button_states()



        # Sync progress bar / step label if project has state

        if self._project:

            self._progress_bar.setValue(int(self._project.progress_pct))

            self._step_label.setText(self._state_to_step_text(self._project.state))



    # ------------------------------------------------------------------

    # UI construction

    # ------------------------------------------------------------------



    def _build_ui(self) -> None:

        root = QVBoxLayout(self)

        root.setContentsMargins(10, 10, 10, 10)

        root.setSpacing(8)



        # --- Section 1: Generation Control ---

        self._build_control_section(root)



        # --- Section 2: Progress ---

        self._build_progress_section(root)



        # --- Section 3: Chapter Selection ---

        self._build_chapter_selection_section(root)



        # --- Section 4: Live Output Log ---

        self._build_log_section(root)



        # --- Section 5: Context Strategy Info ---

        self._build_context_section(root)



        root.addStretch()



    def _build_control_section(self, parent_layout: QVBoxLayout) -> None:

        group = self._make_groupbox("Generation Control")

        layout = QVBoxLayout(group)

        layout.setSpacing(6)



        # Primary action — large, green

        self._btn_generate_full = QPushButton("Generate Full Book")

        self._btn_generate_full.setStyleSheet(_GREEN_BUTTON)

        self._btn_generate_full.setCursor(Qt.CursorShape.PointingHandCursor)

        self._btn_generate_full.clicked.connect(lambda: self._start_generation("full"))

        layout.addWidget(self._btn_generate_full)



        # Secondary actions row

        row1 = QHBoxLayout()

        self._btn_generate_outline = QPushButton("Generate Outline Only")

        self._btn_generate_outline.setStyleSheet(_DARK_BUTTON)

        self._btn_generate_outline.clicked.connect(lambda: self._start_generation("outline"))

        row1.addWidget(self._btn_generate_outline)



        self._btn_generate_selected = QPushButton("Generate Selected Chapters")

        self._btn_generate_selected.setStyleSheet(_DARK_BUTTON)

        self._btn_generate_selected.clicked.connect(lambda: self._start_generation("selected"))

        row1.addWidget(self._btn_generate_selected)

        layout.addLayout(row1)



        # Control row

        row2 = QHBoxLayout()

        self._btn_pause = QPushButton("Pause")

        self._btn_pause.setStyleSheet(_DARK_BUTTON)

        self._btn_pause.clicked.connect(self._pause_generation)

        row2.addWidget(self._btn_pause)



        self._btn_resume = QPushButton("Resume")

        self._btn_resume.setStyleSheet(_DARK_BUTTON)

        self._btn_resume.clicked.connect(self._resume_generation)

        row2.addWidget(self._btn_resume)



        self._btn_cancel = QPushButton("Cancel")

        self._btn_cancel.setStyleSheet(_ACCENT_BUTTON = f"""

QPushButton {{

    background: {CATPPUCCIN_BLUE};

    color: {CATPPUCCIN_BG};

    border: none;

    border-radius: 4px;

    padding: 6px 14px;

    font-size: 12px;

    font-weight: bold;

}}

QPushButton:hover {{

    background: #b4befe;

}}

QPushButton:disabled {{

    background: {CATPPUCCIN_SURFACE};

    color: {CATPPUCCIN_BORDER};

}}

"""



_RED_BUTTON)

        self._btn_cancel.clicked.connect(self._stop_generation)

        row2.addWidget(self._btn_cancel)

        layout.addLayout(row2)



        parent_layout.addWidget(group)



    def _build_progress_section(self, parent_layout: QVBoxLayout) -> None:

        group = self._make_groupbox("Progress")

        layout = QVBoxLayout(group)

        layout.setSpacing(4)



        self._progress_bar = QProgressBar()

        self._progress_bar.setRange(0, 100)

        self._progress_bar.setValue(0)

        self._progress_bar.setFormat("%p%")

        self._progress_bar.setStyleSheet(_PROGRESS_BAR)

        layout.addWidget(self._progress_bar)



        self._step_label = QLabel("Idle — ready to generate.")

        self._step_label.setStyleSheet(_LABEL_STYLE)

        self._step_label.setWordWrap(True)

        layout.addWidget(self._step_label)



        self._elapsed_label = QLabel("Elapsed: 00:00:00")

        self._elapsed_label.setStyleSheet(_SUB_LABEL_STYLE)

        layout.addWidget(self._elapsed_label)



        parent_layout.addWidget(group)



    def _build_chapter_selection_section(self, parent_layout: QVBoxLayout) -> None:

        group = self._make_groupbox("Chapter Selection")

        layout = QVBoxLayout(group)

        layout.setSpacing(4)



        self._chapter_list = QListWidget()

        self._chapter_list.setStyleSheet(_LIST_WIDGET)

        layout.addWidget(self._chapter_list)



        btn_row = QHBoxLayout()

        self._btn_select_all = QPushButton("Select All")

        self._btn_select_all.setStyleSheet(_DARK_BUTTON)

        self._btn_select_all.clicked.connect(self._select_all_chapters)

        btn_row.addWidget(self._btn_select_all)



        self._btn_deselect_all = QPushButton("Deselect All")

        self._btn_deselect_all.setStyleSheet(_DARK_BUTTON)

        self._btn_deselect_all.clicked.connect(self._deselect_all_chapters)

        btn_row.addWidget(self._btn_deselect_all)

        layout.addLayout(btn_row)



        parent_layout.addWidget(group)



        self._rebuild_chapter_list()



    def _build_log_section(self, parent_layout: QVBoxLayout) -> None:

        group = self._make_groupbox("Live Output Log")

        layout = QVBoxLayout(group)

        layout.setSpacing(4)



        self._log_edit = QTextEdit()

        self._log_edit.setReadOnly(True)

        self._log_edit.setStyleSheet(_LOG_EDIT)

        self._log_edit.setMinimumHeight(160)

        layout.addWidget(self._log_edit)



        self._btn_clear_log = QPushButton("Clear Log")

        self._btn_clear_log.setStyleSheet(_DARK_BUTTON)

        self._btn_clear_log.setFixedWidth(120)

        self._btn_clear_log.clicked.connect(self._clear_log)

        layout.addWidget(self._btn_clear_log, alignment=Qt.AlignmentFlag.AlignRight)



        parent_layout.addWidget(group)



    def _build_context_section(self, parent_layout: QVBoxLayout) -> None:

        group = self._make_groupbox("Context Strategy Info")

        layout = QVBoxLayout(group)

        layout.setSpacing(4)



        self._context_strategy_label = QLabel("Strategy: —")

        self._context_strategy_label.setStyleSheet(_LABEL_STYLE)

        self._context_strategy_label.setWordWrap(True)

        layout.addWidget(self._context_strategy_label)



        self._context_budget_label = QLabel("Budget: —")

        self._context_budget_label.setStyleSheet(_SUB_LABEL_STYLE)

        self._context_budget_label.setWordWrap(True)

        layout.addWidget(self._context_budget_label)



        # Batch operations

        batch_row = QHBoxLayout()

        self._btn_parse_outline = QPushButton("Parse Outline")

        self._btn_parse_outline.setStyleSheet(_ACCENT_BUTTON)

        self._btn_parse_outline.setToolTip("Auto-populate chapter titles & synopses from the outline")

        self._btn_parse_outline.clicked.connect(self._on_parse_outline)

        batch_row.addWidget(self._btn_parse_outline)



        self._btn_clear_all = QPushButton("Clear All Content")

        self._btn_clear_all.clicked.connect(self._on_clear_all)

        batch_row.addWidget(self._btn_clear_all)



        self._btn_regenerate_all = QPushButton("Regenerate All")

        self._btn_regenerate_all.clicked.connect(self._on_regenerate_all)

        batch_row.addWidget(self._btn_regenerate_all)

        layout.addLayout(batch_row)



        self._btn_context_report = QPushButton("Show Context Report")

        self._btn_context_report.setStyleSheet(_DARK_BUTTON)

        self._btn_context_report.setFixedWidth(180)

        self._btn_context_report.clicked.connect(self._show_context_report)

        layout.addWidget(self._btn_context_report, alignment=Qt.AlignmentFlag.AlignLeft)



        parent_layout.addWidget(group)

        self._update_context_info()



    # ------------------------------------------------------------------

    # Helpers — UI

    # ------------------------------------------------------------------



    @staticmethod

    def _make_groupbox(title: str) -> object:

        """Create a styled QGroupBox.  Returned as object to avoid type-check issues."""

        from PySide6.QtWidgets import QGroupBox

        gb = QGroupBox(title)

        gb.setStyleSheet(_DARK_GROUPBOX)

        return gb



    def _rebuild_chapter_list(self) -> None:

        """Repopulate the chapter check-list from the project."""

        self._chapter_list.blockSignals(True)

        current_project = self._project

        self._chapter_list.clear()

        if not current_project:

            self._chapter_list.blockSignals(False)

            return



        # Remember which indices were previously checked

        previously_checked: set[int] = set()

        for i in range(self._chapter_list.count()):

            item = self._chapter_list.item(i)

            if item and item.checkState() == Qt.CheckState.Checked:

                previously_checked.add(i)



        for ch in current_project.chapters:

            item = QListWidgetItem(f"Chapter {ch.index + 1}: {ch.title}")

            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)

            item.setCheckState(

                Qt.CheckState.Checked

                if ch.index in previously_checked or not previously_checked

                else Qt.CheckState.Unchecked

            )

            if ch.content_generated:

                item.setText(f"✓ {item.text()}")

            self._chapter_list.addItem(item)



        self._chapter_list.blockSignals(False)



    def _get_checked_chapter_indices(self) -> list[int]:

        """Return the 0-based indices of checked chapters."""

        indices: list[int] = []

        for i in range(self._chapter_list.count()):

            item = self._chapter_list.item(i)

            if item and item.checkState() == Qt.CheckState.Checked:

                indices.append(i)

        return indices



    def _select_all_chapters(self) -> None:

        for i in range(self._chapter_list.count()):

            item = self._chapter_list.item(i)

            if item:

                item.setCheckState(Qt.CheckState.Checked)



    def _deselect_all_chapters(self) -> None:

        for i in range(self._chapter_list.count()):

            item = self._chapter_list.item(i)

            if item:

                item.setCheckState(Qt.CheckState.Unchecked)



    def _clear_log(self) -> None:

        self._log_edit.clear()



    def _update_context_info(self) -> None:

        if not self._project:

            self._context_strategy_label.setText("Strategy: —")

            self._context_budget_label.setText("Budget: —")

            return



        strategy = self._project.generation_config.context_strategy

        label = strategy.replace("_", " ").title()

        self._context_strategy_label.setText(f"Strategy: {label}")

        self._context_budget_label.setText(

            "Budget: Context report available via the button below."

        )



    def _show_context_report(self) -> None:

        """Show a dialog with the context engineering report for the next chapter."""

        if not self._project:

            return



        # Determine next chapter to generate

        next_idx = self._project.current_chapter_index + 1

        if next_idx >= len(self._project.chapters):

            next_idx = 0  # wrap around



        try:

            report = self._harness._context_eng.get_context_report(next_idx)

        except Exception:

            report = "Unable to generate context report."



        dlg = QDialog(self)

        dlg.setWindowTitle(f"Context Report — Chapter {next_idx + 1}")

        dlg.setMinimumSize(520, 380)

        dlg.setStyleSheet(

            f"QDialog {{ background: {CATPPUCCIN_BG}; }}"

            f"QLabel {{ color: {CATPPUCCIN_TEXT}; font-size: 13px; }}"

            f"QTextEdit {{ background: {CATPPUCCIN_SURFACE}; color: {CATPPUCCIN_TEXT}; "

            f"border: 1px solid {CATPPUCCIN_BORDER}; border-radius: 4px; "

            f"font-family: monospace; font-size: 12px; padding: 6px; }}"

            f"QPushButton {{ background: {CATPPUCCIN_BORDER}; color: {CATPPUCCIN_TEXT}; "

            f"border: none; border-radius: 4px; padding: 6px 18px; }}"

            f"QPushButton:hover {{ background: {CATPPUCCIN_ACCENT}; color: {CATPPUCCIN_BG}; }}"

        )



        layout = QVBoxLayout(dlg)

        header = QLabel(f"Context engineering report for Chapter {next_idx + 1}:")

        layout.addWidget(header)



        text_edit = QTextEdit()

        text_edit.setReadOnly(True)

        text_edit.setPlainText(report)

        layout.addWidget(text_edit)



        close_btn = QPushButton("Close")

        close_btn.clicked.connect(dlg.accept)

        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)



        dlg.exec()



    # ------------------------------------------------------------------

    # Logging

    # ------------------------------------------------------------------



    def log(self, message: str) -> None:

        """Append a timestamped message to the output log."""

        ts = time.strftime("%H:%M:%S")

        self._log_edit.append(f"[{ts}] {message}")

        # Auto-scroll to bottom

        scrollbar = self._log_edit.verticalScrollBar()

        scrollbar.setValue(scrollbar.maximum())



    def append_output(self, text: str) -> None:

        """Append raw generated text to the output log (no timestamp prefix).



        Called directly from harness signals — intentionally NOT a @Slot.

        """

        cursor = self._log_edit.textCursor()

        cursor.movePosition(cursor.MoveOperation.End)

        cursor.insertText(text)

        self._log_edit.setTextCursor(cursor)

        self._log_edit.ensureCursorVisible()



    # ------------------------------------------------------------------

    # Generation lifecycle

    # ------------------------------------------------------------------



    def _start_generation(self, mode: str) -> None:

        """Kick off generation in a worker thread.



        Parameters

        ----------

        mode: "full", "outline", or "selected"

        """

        if not self._project:

            self.log("ERROR: No project loaded.")

            return



        if mode == "selected":

            checked = self._get_checked_chapter_indices()

            if not checked:

                self.log("ERROR: No chapters selected for generation.")

                return

            self._project.generation_config.chapters_to_generate = checked

            self.log(f"Starting generation of {len(checked)} selected chapters…")

        elif mode == "outline":

            self._project.generation_config.chapters_to_generate = []

            self.log("Starting outline-only generation…")

        else:  # full

            self._project.generation_config.chapters_to_generate = []

            self.log("Starting full book generation…")



        # Make sure the harness knows about this project

        self._harness.set_project(self._project)



        # For outline-only mode we rely on the harness pipeline skipping

        # chapters when none are listed — but the harness always runs

        # generate_full_book.  For pure outline we clear chapters_to_generate

        # and the pipeline will stop after outline + front/back matter.

        if mode == "outline":

            # Temporarily disable chapter/front/back generation

            self._saved_chapters = self._project.generation_config.chapters_to_generate

            self._saved_frontmatter = self._project.generation_config.include_frontmatter

            self._saved_backmatter = self._project.generation_config.include_backmatter

            self._project.generation_config.chapters_to_generate = []  # empty = skip all

            self._project.generation_config.include_frontmatter = False

            self._project.generation_config.include_backmatter = False



        # Create and start the worker

        self._worker = GenerationWorker(self._harness, parent=self)

        self._worker.finished_signal.connect(self._on_generation_finished)

        self._worker.error_signal.connect(self._on_generation_error)

        self._worker.start()



        # Start elapsed timer

        self._elapsed_seconds = 0

        self._update_elapsed_display()

        self._timer.start()



        self._update_button_states()



    def _stop_generation(self) -> None:

        """Cancel the current generation."""

        self._harness.cancel()



    def _pause_generation(self) -> None:

        """Pause the current generation."""

        self._harness.pause()



    def _resume_generation(self) -> None:

        """Resume a paused generation."""

        self._harness.resume()



    # ------------------------------------------------------------------

    # Elapsed time

    # ------------------------------------------------------------------



    def _tick_elapsed(self) -> None:

        self._elapsed_seconds += 1

        self._update_elapsed_display()



    def _update_elapsed_display(self) -> None:

        h = self._elapsed_seconds // 3600

        m = (self._elapsed_seconds % 3600) // 60

        s = self._elapsed_seconds % 60

        self._elapsed_label.setText(f"Elapsed: {h:02d}:{m:02d}:{s:02d}")



    # ------------------------------------------------------------------

    # Harness signal handlers

    # ------------------------------------------------------------------



    def _connect_harness_signals(self) -> None:

        self._harness.state_changed.connect(self._on_state_changed)

        self._harness.progress_changed.connect(self._on_progress_changed)

        self._harness.log_message.connect(self.log)

        self._harness.chapter_progress.connect(self.append_output)



    def _on_state_changed(self, state_value: str) -> None:

        """Handle harness.state_changed signal."""

        self._step_label.setText(self._state_to_step_text(GenerationState(state_value)))

        self._update_button_states()



    def _on_progress_changed(self, pct: float) -> None:

        """Handle harness.progress_changed signal."""

        self._progress_bar.setValue(int(pct))



    def _on_generation_finished(self) -> None:

        """Handle worker.finished_signal."""

        self._timer.stop()

        self._worker = None

        self._update_button_states()

        self.log("Generation worker finished.")



    def _on_generation_error(self, error_msg: str) -> None:

        """Handle worker.error_signal."""

        self._timer.stop()

        self.log(f"ERROR: {error_msg}")



    def _on_parse_outline(self) -> None:

        """Auto-populate chapter titles and synopses from the outline text."""

        from ..ai.outline_parser import parse_outline_to_chapters, apply_parsed_chapters_to_project

        outline = self._project.outline

        if not outline.strip():

            self.log("No outline to parse.")

            return

        parsed = parse_outline_to_chapters(outline)

        if not parsed:

            self.log("No chapter headings found in outline. Expected 'Chapter N: Title' format.")

            return

        count = apply_parsed_chapters_to_project(self._project, parsed)

        self.log(f"Parsed {count} chapters from outline.")

        self._refresh_chapter_list()

        self.log_message.emit(f"Outline parsed: {count} chapters auto-populated.")



    def _on_clear_all(self) -> None:

        """Clear all generated chapter content (keeps titles and synopses)."""

        for ch in self._project.chapters:

            ch.content_markdown = ""

            ch.content_generated = False

            ch.word_count = 0

        self.log("Cleared all chapter content.")

        self._refresh_chapter_list()

        self.log_message.emit("All chapter content cleared.")



    def _on_regenerate_all(self) -> None:

        """Mark all chapters as not generated so they will be regenerated."""

        for ch in self._project.chapters:

            ch.content_generated = False

        self.log("All chapters marked for regeneration.")

        self._refresh_chapter_list()



    # ------------------------------------------------------------------

    # Button enable / disable logic

    # ------------------------------------------------------------------



    def _update_button_states(self) -> None:

        """Enable/disable buttons based on current generation state."""

        if not self._project:

            is_running = False

        else:

            state = self._project.state

            is_running = state in (

                GenerationState.PLANNING,

                GenerationState.GENERATING_OUTLINE,

                GenerationState.GENERATING_CHAPTER,

                GenerationState.GENERATING_FRONTMATTER,

                GenerationState.GENERATING_BACKMATTER,

                GenerationState.POST_PROCESSING,

            )

            is_paused = state == GenerationState.PAUSED

            is_idle = state in (

                GenerationState.IDLE,

                GenerationState.COMPLETED,

                GenerationState.CANCELLED,

                GenerationState.ERROR,

            )



        # Generate buttons: enabled only when idle

        self._btn_generate_full.setEnabled(is_idle if self._project else False)

        self._btn_generate_outline.setEnabled(is_idle if self._project else False)

        self._btn_generate_selected.setEnabled(is_idle if self._project else False)



        # Pause: only while running (not already paused)

        self._btn_pause.setEnabled(is_running)



        # Resume: only while paused

        self._btn_resume.setEnabled(is_paused if self._project else False)



        # Cancel: while running or paused

        self._btn_cancel.setEnabled(is_running or (is_paused if self._project else False))



    # ------------------------------------------------------------------

    # Helpers

    # ------------------------------------------------------------------



    @staticmethod

    def _state_to_step_text(state: GenerationState) -> str:

        """Return a human-readable description for a generation state."""

        mapping = {

            GenerationState.IDLE: "Idle — ready to generate.",

            GenerationState.PLANNING: "Planning generation…",

            GenerationState.GENERATING_OUTLINE: "Generating book outline…",

            GenerationState.GENERATING_CHAPTER: "Generating chapters…",

            GenerationState.GENERATING_FRONTMATTER: "Generating front matter…",

            GenerationState.GENERATING_BACKMATTER: "Generating back matter…",

            GenerationState.POST_PROCESSING: "Post-processing…",

            GenerationState.PAUSED: "Generation paused.",

            GenerationState.CANCELLED: "Generation cancelled.",

            GenerationState.COMPLETED: "Generation completed.",

            GenerationState.ERROR: "Generation encountered an error.",

        }

        return mapping.get(state, str(state))