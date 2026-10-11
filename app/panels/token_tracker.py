"""Token Tracker panel — displays token usage statistics and per-chapter breakdown."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..models.book_project import BookProject
from ..models.extended_models import TokenUsageEntry, TokenUsageTracker

# ---------------------------------------------------------------------------
# Catppuccin Mocha dark palette
# ---------------------------------------------------------------------------
CATPPUCCIN_BG = "#1e1e2e"
CATPPUCCIN_TEXT = "#cdd6f4"
CATPPUCCIN_SUBTEXT = "#a6adc8"
CATPPUCCIN_ACCENT = "#89b4fa"
CATPPUCCIN_BORDER = "#313244"
CATPPUCCIN_SURFACE = "#181825"
CATPPUCCIN_GREEN = "#a6e3a1"
CATPPUCCIN_RED = "#f38ba8"
CATPPUCCIN_YELLOW = "#f9e2af"
CATPPUCCIN_MAUVE = "#cba6f7"
CATPPUCCIN_BLUE = "#89b4fa"
CATPPUCCIN_TEAL = "#94e2d5"
CATPPUCCIN_PEACH = "#fab387"
CATPPUCCIN_OVERLAY = "#313244"

# ---------------------------------------------------------------------------
# Stylesheet fragments
# ---------------------------------------------------------------------------
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

_RED_BUTTON = f"""
QPushButton {{
    background: {CATPPUCCIN_RED};
    color: {CATPPUCCIN_BG};
    border: none;
    border-radius: 4px;
    padding: 6px 14px;
    font-size: 13px;
    font-weight: bold;
}}
QPushButton:hover {{
    background: #eba0ac;
}}
"""

_TABLE_STYLE = f"""
QTableWidget {{
    background: {CATPPUCCIN_SURFACE};
    color: {CATPPUCCIN_TEXT};
    border: 1px solid {CATPPUCCIN_BORDER};
    border-radius: 4px;
    gridline-color: {CATPPUCCIN_BORDER};
    font-size: 13px;
    selection-background-color: {CATPPUCCIN_OVERLAY};
}}
QTableWidget::item {{
    padding: 4px 8px;
}}
QTableWidget::item:selected {{
    background: {CATPPUCCIN_OVERLAY};
}}
QHeaderView::section {{
    background: {CATPPUCCIN_BG};
    color: {CATPPUCCIN_TEXT};
    border: 1px solid {CATPPUCCIN_BORDER};
    padding: 6px 8px;
    font-weight: bold;
    font-size: 12px;
}}
QTableWidget QTableCornerButton::section {{
    background: {CATPPUCCIN_BG};
    border: 1px solid {CATPPUCCIN_BORDER};
}}
"""

_BAR_CHART_STYLE = f"""
QTextEdit {{
    background: {CATPPUCCIN_SURFACE};
    color: {CATPPUCCIN_TEXT};
    border: 1px solid {CATPPUCCIN_BORDER};
    border-radius: 4px;
    font-family: "Fira Code", "JetBrains Mono", "Consolas", monospace;
    font-size: 13px;
    padding: 8px;
}}
"""

_SUMMARY_LABEL_STYLE = f"color: {CATPPUCCIN_SUBTEXT}; font-size: 13px;"
_SUMMARY_VALUE_STYLE = f"color: {CATPPUCCIN_ACCENT}; font-size: 18px; font-weight: bold;"
_SUMMARY_TOTAL_STYLE = f"color: {CATPPUCCIN_GREEN}; font-size: 18px; font-weight: bold;"

# Color map for row highlighting
_ROW_COLORS = {
    "outline": CATPPUCCIN_MAUVE,
    "chapter": CATPPUCCIN_BLUE,
    "summary": CATPPUCCIN_GREEN,
    "refine": CATPPUCCIN_YELLOW,
}

_MAX_BAR_WIDTH = 50  # characters for the bar chart


class TokenTrackerPanel(QWidget):
    """Panel that displays token usage statistics and a per-chapter breakdown."""

    def __init__(self, project: BookProject, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._project = project
        self._build_ui()
        self.refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_project(self, project: BookProject) -> None:
        """Switch to a different project."""
        self._project = project
        self.refresh()

    def refresh(self) -> None:
        """Re-sync the UI with the current project's token usage data."""
        tracker = self._get_tracker()
        self._update_summary(tracker)
        self._update_table(tracker)
        self._update_bar_chart(tracker)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # Section 1: Summary
        self._build_summary_section(root)

        # Section 2: Per-Chapter Breakdown table
        self._build_table_section(root)

        # Section 3: Token Usage Over Time (bar chart)
        self._build_bar_chart_section(root)

        # Bottom buttons
        self._build_button_row(root)

        root.addStretch()

    def _build_summary_section(self, parent_layout: QVBoxLayout) -> None:
        group = self._make_groupbox("Summary")
        form = QFormLayout(group)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(6)

        # Total Tokens — large, bold, accent green
        self._lbl_total_tokens = QLabel("0")
        self._lbl_total_tokens.setStyleSheet(_SUMMARY_TOTAL_STYLE)
        form.addRow(self._styled_form_label("Total Tokens"), self._lbl_total_tokens)

        # Prompt Tokens
        self._lbl_prompt_tokens = QLabel("0")
        self._lbl_prompt_tokens.setStyleSheet(_SUMMARY_VALUE_STYLE)
        form.addRow(self._styled_form_label("Prompt Tokens"), self._lbl_prompt_tokens)

        # Completion Tokens
        self._lbl_completion_tokens = QLabel("0")
        self._lbl_completion_tokens.setStyleSheet(_SUMMARY_VALUE_STYLE)
        form.addRow(self._styled_form_label("Completion Tokens"), self._lbl_completion_tokens)

        # Total Duration
        self._lbl_total_duration = QLabel("0.0s")
        self._lbl_total_duration.setStyleSheet(_SUMMARY_VALUE_STYLE)
        form.addRow(self._styled_form_label("Total Duration"), self._lbl_total_duration)

        # Speed
        self._lbl_speed = QLabel("0.0 tok/s")
        self._lbl_speed.setStyleSheet(_SUMMARY_VALUE_STYLE)
        form.addRow(self._styled_form_label("Speed"), self._lbl_speed)

        # Total API Calls
        self._lbl_api_calls = QLabel("0")
        self._lbl_api_calls.setStyleSheet(_SUMMARY_VALUE_STYLE)
        form.addRow(self._styled_form_label("Total API Calls"), self._lbl_api_calls)

        parent_layout.addWidget(group)

    def _build_table_section(self, parent_layout: QVBoxLayout) -> None:
        group = self._make_groupbox("Per-Chapter Breakdown")
        layout = QVBoxLayout(group)
        layout.setSpacing(4)

        self._table = QTableWidget()
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels([
            "Chapter", "Stage", "Prompt Tokens", "Completion Tokens",
            "Total", "Duration", "Speed",
        ])
        self._table.setSortingEnabled(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setStyleSheet(_TABLE_STYLE)
        self._table.horizontalHeader().setStretchLastSection(True)
        # Resize columns to fit content
        self._table.horizontalHeader().setSectionResizeMode(
            0, QTableWidget.ResizeMode.ResizeToContents,
        )
        self._table.horizontalHeader().setSectionResizeMode(
            1, QTableWidget.ResizeMode.ResizeToContents,
        )
        layout.addWidget(self._table)

        parent_layout.addWidget(group)

    def _build_bar_chart_section(self, parent_layout: QVBoxLayout) -> None:
        group = self._make_groupbox("Token Usage Over Time")
        layout = QVBoxLayout(group)
        layout.setSpacing(4)

        self._bar_chart = QTextEdit()
        self._bar_chart.setReadOnly(True)
        self._bar_chart.setStyleSheet(_BAR_CHART_STYLE)
        self._bar_chart.setMinimumHeight(180)
        layout.addWidget(self._bar_chart)

        parent_layout.addWidget(group)

    def _build_button_row(self, parent_layout: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.setSpacing(8)

        self._btn_export = QPushButton("Export Usage Report")
        self._btn_export.setStyleSheet(_DARK_BUTTON)
        self._btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_export.clicked.connect(self._export_report)
        row.addWidget(self._btn_export)

        self._btn_clear = QPushButton("Clear History")
        self._btn_clear.setStyleSheet(_RED_BUTTON)
        self._btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_clear.clicked.connect(self._clear_history)
        row.addWidget(self._btn_clear)

        row.addStretch()
        parent_layout.addLayout(row)

    # ------------------------------------------------------------------
    # Data updates
    # ------------------------------------------------------------------

    def _get_tracker(self) -> TokenUsageTracker:
        """Return the project's token usage tracker, creating one if needed."""
        if self._project and self._project.token_usage is not None:
            return self._project.token_usage  # type: ignore[return-value]
        return TokenUsageTracker()

    def _update_summary(self, tracker: TokenUsageTracker) -> None:
        """Populate the summary labels from tracker totals."""
        total = tracker.total_tokens
        prompt = tracker.total_prompt_tokens
        completion = tracker.total_completion_tokens
        duration = tracker.total_duration
        speed = tracker.tokens_per_second
        calls = len(tracker.entries)

        self._lbl_total_tokens.setText(f"{total:,}")
        self._lbl_prompt_tokens.setText(f"{prompt:,}")
        self._lbl_completion_tokens.setText(f"{completion:,}")

        # Format duration nicely
        if duration >= 3600:
            h = int(duration // 3600)
            m = int((duration % 3600) // 60)
            s = int(duration % 60)
            self._lbl_total_duration.setText(f"{h}h {m}m {s}s")
        elif duration >= 60:
            m = int(duration // 60)
            s = int(duration % 60)
            self._lbl_total_duration.setText(f"{m}m {s}s")
        else:
            self._lbl_total_duration.setText(f"{duration:.1f}s")

        self._lbl_speed.setText(f"{speed:.1f} tok/s")
        self._lbl_api_calls.setText(str(calls))

    def _update_table(self, tracker: TokenUsageTracker) -> None:
        """Populate the per-chapter breakdown table."""
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)

        for i, entry in enumerate(tracker.entries):
            row = self._table.rowCount()
            self._table.insertRow(row)

            # Determine chapter number from stage
            chapter_label = self._extract_chapter_label(entry.stage)

            # Chapter column
            item_chapter = QTableWidgetItem(chapter_label)
            item_chapter.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 0, item_chapter)

            # Stage column
            item_stage = QTableWidgetItem(entry.stage)
            item_stage.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 1, item_stage)

            # Prompt Tokens
            item_prompt = QTableWidgetItem(f"{entry.prompt_tokens:,}")
            item_prompt.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 2, item_prompt)

            # Completion Tokens
            item_comp = QTableWidgetItem(f"{entry.completion_tokens:,}")
            item_comp.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 3, item_comp)

            # Total
            item_total = QTableWidgetItem(f"{entry.total_tokens:,}")
            item_total.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 4, item_total)

            # Duration
            if entry.duration_seconds >= 60:
                dur_str = f"{entry.duration_seconds / 60:.1f}m"
            else:
                dur_str = f"{entry.duration_seconds:.1f}s"
            item_dur = QTableWidgetItem(dur_str)
            item_dur.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 5, item_dur)

            # Speed
            if entry.duration_seconds > 0:
                spd = entry.completion_tokens / entry.duration_seconds
                spd_str = f"{spd:.1f} tok/s"
            else:
                spd_str = "—"
            item_spd = QTableWidgetItem(spd_str)
            item_spd.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 6, item_spd)

            # Color-code the row based on stage type
            row_color = self._row_color_for_stage(entry.stage)
            if row_color:
                bg = QColor(row_color)
                # Use a semi-transparent version as background
                bg.setAlpha(35)
                fg = QColor(CATPPUCCIN_TEXT)
                for col in range(7):
                    item = self._table.item(row, col)
                    if item:
                        item.setBackground(bg)
                        item.setForeground(fg)

        self._table.setSortingEnabled(True)

    def _update_bar_chart(self, tracker: TokenUsageTracker) -> None:
        """Render a text-based horizontal bar chart in the QTextEdit."""
        if not tracker.entries:
            self._bar_chart.setHtml(
                f'<span style="color: {CATPPUCCIN_SUBTEXT};">'
                "No token usage data yet. Generate content to see usage statistics."
                "</span>"
            )
            return

        max_tokens = max((e.total_tokens for e in tracker.entries), default=1)
        if max_tokens == 0:
            max_tokens = 1

        # Find the longest label for alignment
        max_label_len = max(len(e.stage) for e in tracker.entries)

        lines: list[str] = []
        for entry in tracker.entries:
            # Calculate bar width proportional to max
            bar_len = int((entry.total_tokens / max_tokens) * _MAX_BAR_WIDTH)
            bar_len = max(bar_len, 1)
            bar = "█" * bar_len

            # Pad label for alignment
            label = entry.stage.ljust(max_label_len)

            # Determine bar color based on stage
            bar_color = self._bar_color_for_stage(entry.stage)

            lines.append(
                f'<span style="color: {CATPPUCCIN_TEXT};">{label}</span>'
                f' <span style="color: {CATPPUCCIN_SUBTEXT};">│</span>'
                f'<span style="color: {bar_color};">{bar}</span>'
                f' <span style="color: {CATPPUCCIN_SUBTEXT};">│</span>'
                f' <span style="color: {CATPPUCCIN_TEXT};">{entry.total_tokens:,} tok</span>'
            )

        html = "<br>".join(lines)
        self._bar_chart.setHtml(html)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _export_report(self) -> None:
        """Export the full token usage breakdown to a .txt file."""
        tracker = self._get_tracker()

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Usage Report",
            f"{self._project.name}_token_usage.txt" if self._project else "token_usage.txt",
            "Text Files (*.txt);;All Files (*)",
        )
        if not path:
            return

        lines: list[str] = []
        lines.append("=" * 70)
        lines.append(f"TOKEN USAGE REPORT — {self._project.name if self._project else 'Unknown'}")
        lines.append("=" * 70)
        lines.append("")

        # Summary
        lines.append("— SUMMARY —")
        lines.append(f"  Total Tokens:       {tracker.total_tokens:,}")
        lines.append(f"  Prompt Tokens:      {tracker.total_prompt_tokens:,}")
        lines.append(f"  Completion Tokens:  {tracker.total_completion_tokens:,}")
        dur = tracker.total_duration
        if dur >= 3600:
            h, remainder = divmod(dur, 3600)
            m, s = divmod(remainder, 60)
            lines.append(f"  Total Duration:     {int(h)}h {int(m)}m {int(s)}s")
        elif dur >= 60:
            m, s = divmod(dur, 60)
            lines.append(f"  Total Duration:     {int(m)}m {int(s)}s")
        else:
            lines.append(f"  Total Duration:     {dur:.1f}s")
        lines.append(f"  Speed:              {tracker.tokens_per_second:.1f} tok/s")
        lines.append(f"  Total API Calls:    {len(tracker.entries)}")
        lines.append("")

        # Per-entry breakdown
        lines.append("— PER-CALL BREAKDOWN —")
        lines.append(
            f"  {'Stage':<20} {'Prompt':>10} {'Completion':>12} "
            f"{'Total':>10} {'Duration':>10} {'Speed':>12}"
        )
        lines.append("-" * 78)
        for entry in tracker.entries:
            dur_s = entry.duration_seconds
            if dur_s >= 60:
                dur_str = f"{dur_s / 60:.1f}m"
            else:
                dur_str = f"{dur_s:.1f}s"
            spd = f"{entry.completion_tokens / dur_s:.1f} tok/s" if dur_s > 0 else "—"
            lines.append(
                f"  {entry.stage:<20} {entry.prompt_tokens:>10,} {entry.completion_tokens:>12,} "
                f"{entry.total_tokens:>10,} {dur_str:>10} {spd:>12}"
            )
        lines.append("")
        lines.append("=" * 70)

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def _clear_history(self) -> None:
        """Clear all token usage entries."""
        if self._project and self._project.token_usage is not None:
            self._project.token_usage.entries.clear()  # type: ignore[union-attr]
        self.refresh()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_groupbox(title: str) -> QGroupBox:
        """Create a styled QGroupBox."""
        gb = QGroupBox(title)
        gb.setStyleSheet(_DARK_GROUPBOX)
        return gb

    @staticmethod
    def _styled_form_label(text: str) -> QLabel:
        """Create a consistently styled form label."""
        lbl = QLabel(text)
        lbl.setStyleSheet(_SUMMARY_LABEL_STYLE)
        return lbl

    @staticmethod
    def _extract_chapter_label(stage: str) -> str:
        """Extract a human-readable chapter identifier from a stage string.

        Examples:
            "outline"       -> "—"
            "chapter_0"     -> "Ch 1"
            "chapter_5"     -> "Ch 6"
            "summary_0"     -> "Ch 1"
            "refine_2"      -> "Ch 3"
            "frontmatter"   -> "Front"
            "backmatter"    -> "Back"
        """
        if stage == "outline":
            return "—"
        if stage == "frontmatter":
            return "Front"
        if stage == "backmatter":
            return "Back"
        if stage.startswith("chapter_"):
            try:
                idx = int(stage.split("_", 1)[1])
                return f"Ch {idx + 1}"
            except (ValueError, IndexError):
                return stage
        if stage.startswith("summary_"):
            try:
                idx = int(stage.split("_", 1)[1])
                return f"Ch {idx + 1}"
            except (ValueError, IndexError):
                return stage
        if stage.startswith("refine_"):
            try:
                idx = int(stage.split("_", 1)[1])
                return f"Ch {idx + 1}"
            except (ValueError, IndexError):
                return stage
        return stage

    @staticmethod
    def _row_color_for_stage(stage: str) -> str:
        """Return the Catppuccin color hex for a given stage type."""
        if stage.startswith("outline"):
            return _ROW_COLORS["outline"]
        if stage.startswith("chapter_"):
            return _ROW_COLORS["chapter"]
        if stage.startswith("summary_"):
            return _ROW_COLORS["summary"]
        if stage.startswith("refine_"):
            return _ROW_COLORS["refine"]
        return ""

    @staticmethod
    def _bar_color_for_stage(stage: str) -> str:
        """Return the bar color for a given stage (used in the text chart)."""
        if stage.startswith("outline"):
            return _ROW_COLORS["outline"]
        if stage.startswith("chapter_"):
            return _ROW_COLORS["chapter"]
        if stage.startswith("summary_"):
            return _ROW_COLORS["summary"]
        if stage.startswith("refine_"):
            return _ROW_COLORS["refine"]
        if stage == "frontmatter":
            return CATPPUCCIN_TEAL
        if stage == "backmatter":
            return CATPPUCCIN_PEACH
        return CATPPUCCIN_GREEN