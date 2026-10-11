"""Statistics panel — comprehensive book statistics and visual progress tracking."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..models.book_project import BookProject

# ---------------------------------------------------------------------------
# Catppuccin Mocha dark palette
# ---------------------------------------------------------------------------
CATPPUCCIN_BG = "#1e1e2e"
CATPPUCCIN_TEXT = "#cdd6f4"
CATPPUCCIN_SUBTEXT = "#a6adc8"
CATPPUCCIN_ACCENT = "#89b4fa"
CATPPUCCIN_SURFACE = "#313244"
CATPPUCCIN_OVERLAY = "#45475a"
CATPPUCCIN_GREEN = "#a6e3a1"
CATPPUCCIN_RED = "#f38ba8"
CATPPUCCIN_YELLOW = "#f9e2af"

# ---------------------------------------------------------------------------
# Stylesheet
# ---------------------------------------------------------------------------
_PANEL_STYLE = f"""
QWidget#statisticsPanel {{
    background-color: {CATPPUCCIN_BG};
}}
QGroupBox {{
    color: {CATPPUCCIN_TEXT};
    border: 1px solid {CATPPUCCIN_SURFACE};
    border-radius: 8px;
    margin-top: 14px;
    padding: 16px 12px 12px 12px;
    font-size: 13px;
    font-weight: bold;
    background-color: {CATPPUCCIN_BG};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 8px;
    background-color: {CATPPUCCIN_BG};
}}
QLabel {{
    color: {CATPPUCCIN_TEXT};
    font-size: 12px;
    background: transparent;
}}
QProgressBar {{
    border: 1px solid {CATPPUCCIN_SURFACE};
    border-radius: 6px;
    text-align: center;
    color: {CATPPUCCIN_TEXT};
    background-color: {CATPPUCCIN_SURFACE};
    height: 22px;
    font-size: 12px;
}}
QProgressBar::chunk {{
    background-color: {CATPPUCCIN_ACCENT};
    border-radius: 5px;
}}
QTableWidget {{
    background-color: {CATPPUCCIN_BG};
    alternate-background-color: {CATPPUCCIN_SURFACE};
    color: {CATPPUCCIN_TEXT};
    border: 1px solid {CATPPUCCIN_SURFACE};
    border-radius: 6px;
    gridline-color: {CATPPUCCIN_SURFACE};
    font-size: 12px;
    selection-background-color: {CATPPUCCIN_OVERLAY};
}}
QTableWidget::item {{
    padding: 4px 8px;
}}
QTableWidget::item:alternate {{
    background-color: {CATPPUCCIN_SURFACE};
}}
QHeaderView::section {{
    background-color: {CATPPUCCIN_OVERLAY};
    color: {CATPPUCCIN_TEXT};
    border: 1px solid {CATPPUCCIN_SURFACE};
    padding: 6px 8px;
    font-weight: bold;
    font-size: 12px;
}}
QScrollBar:vertical {{
    background: {CATPPUCCIN_BG};
    width: 10px;
    border-radius: 5px;
}}
QScrollBar::handle:vertical {{
    background: {CATPPUCCIN_OVERLAY};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
"""


def _stat_value_widget(value: str, color: str = CATPPUCCIN_ACCENT) -> QWidget:
    """Create a small vertical layout with a large value label and a placeholder
    for a description label that the caller can reparent."""
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)

    value_label = QLabel(value)
    value_label.setFont(QFont("Segoe UI", 22, QFont.Bold))
    value_label.setStyleSheet(f"color: {color}; background: transparent;")
    value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(value_label)

    desc_label = QLabel("")
    desc_label.setStyleSheet(f"color: {CATPPUCCIN_SUBTEXT}; background: transparent; font-size: 11px;")
    desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(desc_label)

    return container, value_label, desc_label


class StatisticsPanel(QWidget):
    """Comprehensive book statistics and visual progress tracking."""

    def __init__(self, project: BookProject) -> None:
        super().__init__()
        self._project = project
        self._setup_ui()
        self.refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_project(self, project: BookProject) -> None:
        self._project = project
        self.refresh()

    def refresh(self) -> None:
        self._refresh_overview()
        self._refresh_chapter_lengths()
        self._refresh_progress()
        self._refresh_table()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        self.setObjectName("statisticsPanel")
        self.setStyleSheet(_PANEL_STYLE)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        self._main_layout = QVBoxLayout(content)
        self._main_layout.setContentsMargins(4, 4, 4, 4)
        self._main_layout.setSpacing(12)

        self._build_overview_section()
        self._build_chapter_lengths_section()
        self._build_progress_section()
        self._build_table_section()

        self._main_layout.addStretch(1)

        scroll.setWidget(content)
        outer.addWidget(scroll)

    # -- Section 1: Overview ------------------------------------------

    def _build_overview_section(self) -> None:
        group = QGroupBox("Overview")
        grid = QGridLayout(group)
        grid.setSpacing(16)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)

        # Row 0
        self._ov_total_ch, self._ov_total_ch_val, self._ov_total_ch_lbl = _stat_value_widget("0")
        self._ov_total_ch_lbl.setText("Total Chapters")
        grid.addWidget(self._ov_total_ch, 0, 0)

        self._ov_gen_ch, self._ov_gen_ch_val, self._ov_gen_ch_lbl = _stat_value_widget("0")
        self._ov_gen_ch_lbl.setText("Generated Chapters")
        grid.addWidget(self._ov_gen_ch, 0, 1)

        self._ov_comp, self._ov_comp_val, self._ov_comp_lbl = _stat_value_widget("0%")
        self._ov_comp_lbl.setText("Completion %")
        grid.addWidget(self._ov_comp, 0, 2)

        # Row 1
        self._ov_words, self._ov_words_val, self._ov_words_lbl = _stat_value_widget("0")
        self._ov_words_lbl.setText("Total Words")
        grid.addWidget(self._ov_words, 1, 0)

        self._ov_avg, self._ov_avg_val, self._ov_avg_lbl = _stat_value_widget("0")
        self._ov_avg_lbl.setText("Avg Words / Chapter")
        grid.addWidget(self._ov_avg, 1, 1)

        self._ov_reading, self._ov_reading_val, self._ov_reading_lbl = _stat_value_widget("0h 0m")
        self._ov_reading_lbl.setText("Est. Reading Time")
        grid.addWidget(self._ov_reading, 1, 2)

        self._main_layout.addWidget(group)

    # -- Section 2: Chapter Lengths -----------------------------------

    def _build_chapter_lengths_section(self) -> None:
        group = QGroupBox("Chapter Lengths")
        layout = QVBoxLayout(group)

        self._chart_edit = QTextEdit()
        self._chart_edit.setReadOnly(True)
        self._chart_edit.setFont(QFont("Consolas", 10) if hasattr(QFont, "StyleHint") else QFont("Monospace", 10))
        self._chart_edit.setMinimumHeight(160)
        self._chart_edit.setMaximumHeight(400)
        self._chart_edit.setStyleSheet(
            f"QTextEdit {{"
            f"  background-color: {CATPPUCCIN_BG};"
            f"  color: {CATPPUCCIN_TEXT};"
            f"  border: 1px solid {CATPPUCCIN_SURFACE};"
            f"  border-radius: 6px;"
            f"  padding: 8px;"
            f"  font-family: 'Consolas', 'Courier New', monospace;"
            f"  font-size: 11px;"
            f"}}"
        )
        layout.addWidget(self._chart_edit)

        self._main_layout.addWidget(group)

    # -- Section 3: Completion Progress -------------------------------

    def _build_progress_section(self) -> None:
        group = QGroupBox("Completion Progress")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        # Chapter progress bar
        lbl1 = QLabel("Chapter Progress")
        lbl1.setStyleSheet(f"font-weight: bold; color: {CATPPUCCIN_TEXT}; background: transparent;")
        layout.addWidget(lbl1)

        self._chapter_bar = QProgressBar()
        self._chapter_bar.setTextVisible(True)
        layout.addWidget(self._chapter_bar)

        # Word target progress bar
        lbl2 = QLabel("Word Target Progress")
        lbl2.setStyleSheet(f"font-weight: bold; color: {CATPPUCCIN_TEXT}; background: transparent; margin-top: 8px;")
        layout.addWidget(lbl2)

        self._word_bar = QProgressBar()
        self._word_bar.setTextVisible(True)
        layout.addWidget(self._word_bar)

        # Summary label
        self._progress_summary = QLabel("")
        self._progress_summary.setWordWrap(True)
        self._progress_summary.setStyleSheet(f"color: {CATPPUCCIN_SUBTEXT}; background: transparent; font-size: 12px; margin-top: 4px;")
        layout.addWidget(self._progress_summary)

        self._main_layout.addWidget(group)

    # -- Section 4: Chapter Details Table -----------------------------

    def _build_table_section(self) -> None:
        group = QGroupBox("Chapter Details")
        layout = QVBoxLayout(group)

        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(["#", "Title", "Words", "Status", "Synopsis"])
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)

        header = self._table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QTableWidget.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QTableWidget.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QTableWidget.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QTableWidget.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QTableWidget.ResizeMode.Stretch)

        layout.addWidget(self._table)

        self._main_layout.addWidget(group)

    # ------------------------------------------------------------------
    # Data refresh helpers
    # ------------------------------------------------------------------

    def _refresh_overview(self) -> None:
        proj = self._project
        total = len(proj.chapters)
        generated = proj.generated_count()
        total_words = proj.total_words()
        pct = int((generated / total * 100)) if total > 0 else 0

        self._ov_total_ch_val.setText(str(total))
        self._ov_gen_ch_val.setText(str(generated))
        self._ov_comp_val.setText(f"{pct}%")

        # Color-code completion
        if pct > 80:
            color = CATPPUCCIN_GREEN
        elif pct > 50:
            color = CATPPUCCIN_YELLOW
        else:
            color = CATPPUCCIN_RED
        self._ov_comp_val.setStyleSheet(
            f"color: {color}; background: transparent; font-size: 22px; font-weight: bold;"
        )

        self._ov_words_val.setText(f"{total_words:,}")

        avg = int(total_words / generated) if generated > 0 else 0
        self._ov_avg_val.setText(f"{avg:,}")

        # Reading time: 250 words per minute
        minutes = total_words / 250
        hours = int(minutes // 60)
        mins = int(minutes % 60)
        self._ov_reading_val.setText(f"{hours}h {mins}m")

    def _refresh_chapter_lengths(self) -> None:
        proj = self._project
        chapters = proj.chapters

        if not chapters:
            self._chart_edit.setHtml(
                f'<span style="color:{CATPPUCCIN_SUBTEXT};">No chapters yet.</span>'
            )
            return

        max_words = max((ch.word_count for ch in chapters if ch.content_generated), default=0)
        if max_words == 0:
            max_words = 1  # avoid division by zero
        bar_width = 40  # max bar characters
        target = proj.generation_config.words_per_chapter
        target_bar_len = int((target / max_words) * bar_width) if max_words else 0

        lines: list[str] = []
        html_parts: list[str] = []

        for i, ch in enumerate(chapters):
            num = i + 1

            if not ch.content_generated:
                label = f"Ch {num:>3}: (not generated)"
                html_parts.append(
                    f'<span style="color:{CATPPUCCIN_SUBTEXT};">{label}</span>'
                )
                continue

            ratio = ch.word_count / max_words
            filled = int(ratio * bar_width)
            bar = "\u2588" * filled
            words_str = f"{ch.word_count:,}"

            # Determine colour
            if target > 0 and ch.word_count < target * 0.5:
                color = CATPPUCCIN_RED
                warning = " \u26a0"
            else:
                color = CATPPUCCIN_ACCENT
                warning = ""

            label = f"Ch {num:>3}: {bar} {words_str} words{warning}"
            html_parts.append(f'<span style="color:{color};">{label}</span>')

        # Target line marker
        if target > 0:
            marker_prefix = f"{' ' * 7}{'\u2588' * target_bar_len}"
            html_parts.append(
                f'<br><span style="color:{CATPPUCCIN_YELLOW};">{marker_prefix} \u2190 target ({target:,})</span>'
            )

        self._chart_edit.setHtml("<br>".join(html_parts))

    def _refresh_progress(self) -> None:
        proj = self._project
        total = len(proj.chapters)
        generated = proj.generated_count()
        total_words = proj.total_words()
        target = proj.generation_config.words_per_chapter

        # Chapter progress
        self._chapter_bar.setMaximum(total if total > 0 else 1)
        self._chapter_bar.setValue(generated)
        self._chapter_bar.setFormat(f"{generated} / {total}")

        # Word target progress
        if target > 0:
            word_target = total * target
            self._word_bar.setMaximum(word_target if word_target > 0 else 1)
            self._word_bar.setValue(min(total_words, word_target))
            word_pct = int((total_words / word_target * 100)) if word_target > 0 else 0
        else:
            self._word_bar.setMaximum(1)
            self._word_bar.setValue(0)
            word_pct = 0

        self._word_bar.setFormat(f"{total_words:,} / {total * target if target else '?':,} ({word_pct}%)")

        ch_pct = int((generated / total * 100)) if total > 0 else 0
        self._progress_summary.setText(
            f"{generated} of {total} chapters complete, {word_pct}% word target reached"
        )

    def _refresh_table(self) -> None:
        proj = self._project
        chapters = proj.chapters

        # Disable sorting while populating
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(chapters))

        for row, ch in enumerate(chapters):
            # # column
            num_item = QTableWidgetItem(str(row + 1))
            num_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            num_item.setFlags(num_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self._table.setItem(row, 0, num_item)

            # Title column
            title_item = QTableWidgetItem(ch.title)
            title_item.setFlags(title_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self._table.setItem(row, 1, title_item)

            # Words column
            words_str = f"{ch.word_count:,}" if ch.content_generated else "—"
            words_item = QTableWidgetItem(words_str)
            words_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            words_item.setFlags(words_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self._table.setItem(row, 2, words_item)

            # Status column
            if ch.content_generated:
                status_text = "Generated"
                status_color = CATPPUCCIN_GREEN
            else:
                status_text = "Not Generated"
                status_color = CATPPUCCIN_SUBTEXT

            status_item = QTableWidgetItem(status_text)
            status_item.setForeground(QColor(status_color))
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self._table.setItem(row, 3, status_item)

            # Synopsis column (truncated to 50 chars)
            synopsis = ch.synopsis or ""
            if len(synopsis) > 50:
                synopsis = synopsis[:47] + "..."
            synopsis_item = QTableWidgetItem(synopsis)
            synopsis_item.setFlags(synopsis_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self._table.setItem(row, 4, synopsis_item)

        # Re-enable sorting
        self._table.setSortingEnabled(True)