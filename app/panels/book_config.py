"""Book configuration panel for setting up ebook project parameters."""

from PySide6.QtCore import Signal
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTextEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..models.book_project import BookProject, EbookType, EBOOK_TYPE_LABELS

_TONE_OPTIONS = ["Default", "Formal", "Casual", "Dramatic", "Warm", "Technical"]

_AUDIENCE_OPTIONS = [
    "General audience",
    "Beginners",
    "Intermediate",
    "Advanced",
    "Professionals",
    "Children (5-8)",
    "Young Adult (12-18)",
]


class BookConfigPanel(QWidget):
    """Panel widget for configuring an ebook project."""

    project_updated = Signal()
    chapters_changed = Signal()
    outline_edited = Signal(str)

    def __init__(self, project: BookProject, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project = project
        self._tone: str = "Default"
        self._updating: bool = False  # guard against recursive signals

        self._build_ui()
        self._populate_from_project()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_project(self, project: BookProject) -> None:
        """Swap the current project and repopulate all fields."""
        self._project = project
        self._populate_from_project()

    def set_outline(self, text: str) -> None:
        """Set the outline text (e.g. when the harness generates one)."""
        self._updating = True
        self._outline_edit.setPlainText(text)
        self._updating = False

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        # Section 1 – Book Type
        root.addWidget(self._build_book_type_group())

        # Section 2 – Book Metadata
        root.addWidget(self._build_metadata_group())

        # Section 3 – Generation Options
        root.addWidget(self._build_generation_options_group())

        # Section 4 – Chapter Outline
        root.addWidget(self._build_outline_group())

        # Section 5 – Chapter List
        root.addWidget(self._build_chapter_list_group())

        root.addStretch()

    # -- Section 1: Book Type --------------------------------------------------

    def _build_book_type_group(self) -> QGroupBox:
        group = QGroupBox("Book Type")
        form = QFormLayout(group)

        # Ebook type combo
        self._type_combo = QComboBox()
        for etype, label in EBOOK_TYPE_LABELS.items():
            self._type_combo.addItem(label, etype.value)
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        form.addRow("Ebook Type:", self._type_combo)

        # Tone combo
        self._tone_combo = QComboBox()
        self._tone_combo.addItems(_TONE_OPTIONS)
        self._tone_combo.currentTextChanged.connect(self._on_tone_changed)
        form.addRow("Tone:", self._tone_combo)

        # Number of chapters
        self._num_chapters_spin = QSpinBox()
        self._num_chapters_spin.setRange(1, 50)
        self._num_chapters_spin.setValue(10)
        self._num_chapters_spin.valueChanged.connect(self._on_num_chapters_changed)
        form.addRow("Chapters:", self._num_chapters_spin)

        # Words per chapter
        self._words_spin = QSpinBox()
        self._words_spin.setRange(500, 10000)
        self._words_spin.setSingleStep(500)
        self._words_spin.setValue(2000)
        self._words_spin.valueChanged.connect(self._on_words_changed)
        form.addRow("Words / Chapter:", self._words_spin)

        # Generate button
        self._generate_btn = QPushButton("Generate Chapter List")
        self._generate_btn.clicked.connect(self._on_generate_chapters)
        form.addRow(self._generate_btn)

        return group

    # -- Section 2: Book Metadata ------------------------------------------------

    def _build_metadata_group(self) -> QGroupBox:
        group = QGroupBox("Book Metadata")
        form = QFormLayout(group)

        self._title_edit = QLineEdit()
        self._title_edit.textEdited.connect(self._on_metadata_changed)
        form.addRow("Title:", self._title_edit)

        self._subtitle_edit = QLineEdit()
        self._subtitle_edit.textEdited.connect(self._on_metadata_changed)
        form.addRow("Subtitle:", self._subtitle_edit)

        self._author_edit = QLineEdit()
        self._author_edit.textEdited.connect(self._on_metadata_changed)
        form.addRow("Author:", self._author_edit)

        self._coauthors_edit = QLineEdit()
        self._coauthors_edit.textEdited.connect(self._on_metadata_changed)
        form.addRow("Co-Authors:", self._coauthors_edit)

        self._genre_edit = QLineEdit()
        self._genre_edit.textEdited.connect(self._on_metadata_changed)
        form.addRow("Genre:", self._genre_edit)

        self._audience_combo = QComboBox()
        self._audience_combo.addItems(_AUDIENCE_OPTIONS)
        self._audience_combo.setEditable(False)
        self._audience_combo.currentTextChanged.connect(self._on_metadata_changed)
        form.addRow("Target Audience:", self._audience_combo)

        self._language_edit = QLineEdit()
        self._language_edit.textEdited.connect(self._on_metadata_changed)
        form.addRow("Language:", self._language_edit)

        self._description_edit = QTextEdit()
        self._description_edit.setFixedHeight(72)  # ~3 lines
        self._description_edit.textChanged.connect(self._on_metadata_changed)
        form.addRow("Description:", self._description_edit)

        return group

    # -- Section 3: Generation Options ------------------------------------------

    def _build_generation_options_group(self) -> QGroupBox:
        group = QGroupBox("Generation Options")
        layout = QVBoxLayout(group)

        self._frontmatter_check = QCheckBox("Include Front Matter")
        self._frontmatter_check.setChecked(True)
        self._frontmatter_check.toggled.connect(self._on_gen_options_changed)
        layout.addWidget(self._frontmatter_check)

        self._backmatter_check = QCheckBox("Include Back Matter")
        self._backmatter_check.setChecked(True)
        self._backmatter_check.toggled.connect(self._on_gen_options_changed)
        layout.addWidget(self._backmatter_check)

        self._toc_check = QCheckBox("Include Table of Contents")
        self._toc_check.setChecked(True)
        self._toc_check.toggled.connect(self._on_gen_options_changed)
        layout.addWidget(self._toc_check)

        self._autosave_check = QCheckBox("Auto-save between chapters")
        self._autosave_check.setChecked(True)
        self._autosave_check.toggled.connect(self._on_gen_options_changed)
        layout.addWidget(self._autosave_check)

        row = QHBoxLayout()
        row.addWidget(QLabel("Save every N chapters:"))
        self._save_interval_spin = QSpinBox()
        self._save_interval_spin.setRange(1, 10)
        self._save_interval_spin.setValue(1)
        self._save_interval_spin.valueChanged.connect(self._on_gen_options_changed)
        row.addWidget(self._save_interval_spin)
        row.addStretch()
        layout.addLayout(row)

        self._pause_check = QCheckBox("Pause between chapters")
        self._pause_check.toggled.connect(self._on_gen_options_changed)
        layout.addWidget(self._pause_check)

        return group

    # -- Section 4: Chapter Outline ---------------------------------------------

    def _build_outline_group(self) -> QGroupBox:
        group = QGroupBox("Chapter Outline")
        layout = QVBoxLayout(group)

        self._outline_edit = QPlainTextEdit()
        self._outline_edit.setFixedHeight(160)  # ~8 lines
        self._outline_edit.textChanged.connect(self._on_outline_changed)
        layout.addWidget(self._outline_edit)

        self._edit_full_btn = QPushButton("Edit in Full")
        self._edit_full_btn.clicked.connect(self._on_edit_outline_full)
        layout.addWidget(self._edit_full_btn)

        return group

    # -- Section 5: Chapter List ------------------------------------------------

    def _build_chapter_list_group(self) -> QGroupBox:
        group = QGroupBox("Chapter List")
        layout = QVBoxLayout(group)

        self._chapter_list = QListWidget()
        self._chapter_list.currentRowChanged.connect(self._on_chapter_selected)
        layout.addWidget(self._chapter_list)

        # Buttons row
        btn_row = QHBoxLayout()
        self._add_chapter_btn = QPushButton("Add Chapter")
        self._add_chapter_btn.clicked.connect(self._on_add_chapter)
        btn_row.addWidget(self._add_chapter_btn)

        self._remove_chapter_btn = QPushButton("Remove Selected")
        self._remove_chapter_btn.clicked.connect(self._on_remove_chapter)
        btn_row.addWidget(self._remove_chapter_btn)

        self._move_up_btn = QPushButton("Move Up")
        self._move_up_btn.clicked.connect(self._on_move_up)
        btn_row.addWidget(self._move_up_btn)

        self._move_down_btn = QPushButton("Move Down")
        self._move_down_btn.clicked.connect(self._on_move_down)
        btn_row.addWidget(self._move_down_btn)

        layout.addLayout(btn_row)

        # Chapter detail editors (shown below the list)
        form = QFormLayout()
        self._ch_title_edit = QLineEdit()
        self._ch_title_edit.textEdited.connect(self._on_ch_title_edited)
        form.addRow("Chapter Title:", self._ch_title_edit)

        self._ch_synopsis_edit = QTextEdit()
        self._ch_synopsis_edit.setFixedHeight(60)
        self._ch_synopsis_edit.textChanged.connect(self._on_ch_synopsis_edited)
        form.addRow("Synopsis:", self._ch_synopsis_edit)

        layout.addLayout(form)

        return group

    # ------------------------------------------------------------------
    # Populate / sync from project
    # ------------------------------------------------------------------

    def _populate_from_project(self) -> None:
        """Fill all widgets from the current project (no signals emitted)."""
        self._updating = True
        try:
            p = self._project

            # Book type
            idx = self._type_combo.findData(p.ebook_type.value)
            self._type_combo.setCurrentIndex(max(idx, 0))

            # Tone (stored locally)
            t_idx = self._tone_combo.findText(self._tone)
            self._tone_combo.setCurrentIndex(max(t_idx, 0))

            # Chapter count / words per chapter
            self._num_chapters_spin.setValue(p.generation_config.total_chapters)
            self._words_spin.setValue(p.generation_config.words_per_chapter)

            # Metadata
            m = p.metadata
            self._title_edit.setText(m.title)
            self._subtitle_edit.setText(m.subtitle)
            self._author_edit.setText(m.author)
            self._coauthors_edit.setText(m.co_authors)
            self._genre_edit.setText(m.genre)
            a_idx = self._audience_combo.findText(m.target_audience)
            self._audience_combo.setCurrentIndex(max(a_idx, 0))
            self._language_edit.setText(m.language)
            self._description_edit.setPlainText(m.description)

            # Generation options
            gc = p.generation_config
            self._frontmatter_check.setChecked(gc.include_frontmatter)
            self._backmatter_check.setChecked(gc.include_backmatter)
            self._toc_check.setChecked(gc.include_toc)
            self._autosave_check.setChecked(gc.auto_save)
            self._save_interval_spin.setValue(gc.save_interval)
            self._pause_check.setChecked(gc.pause_between_chapters)

            # Outline
            self._outline_edit.setPlainText(p.outline)

            # Chapter list
            self._refresh_chapter_list()
        finally:
            self._updating = False

    def _refresh_chapter_list(self) -> None:
        """Rebuild the QListWidget from the project's chapter list."""
        self._chapter_list.blockSignals(True)
        self._chapter_list.clear()
        for i, ch in enumerate(self._project.chapters):
            suffix = " (generated)" if ch.content_generated else ""
            self._chapter_list.addItem(f"Ch {i + 1}: {ch.title}{suffix}")
        self._chapter_list.blockSignals(False)

        # Clear detail editors
        self._ch_title_edit.clear()
        self._ch_synopsis_edit.clear()

    # ------------------------------------------------------------------
    # Slot handlers – Book Type section
    # ------------------------------------------------------------------

    def _on_type_changed(self, index: int) -> None:
        if self._updating:
            return
        value = self._type_combo.itemData(index)
        if value is not None:
            self._project.ebook_type = EbookType(value)
        self.project_updated.emit()

    def _on_tone_changed(self, text: str) -> None:
        if self._updating:
            return
        self._tone = text
        self.project_updated.emit()

    def _on_num_chapters_changed(self, value: int) -> None:
        if self._updating:
            return
        self._project.generation_config.total_chapters = value
        self.project_updated.emit()

    def _on_words_changed(self, value: int) -> None:
        if self._updating:
            return
        self._project.generation_config.words_per_chapter = value
        self.project_updated.emit()

    def _on_generate_chapters(self) -> None:
        n = self._num_chapters_spin.value()
        self._project.chapters.clear()
        for i in range(n):
            self._project.add_chapter(title=f"Chapter {i + 1}")
        self._project.generation_config.total_chapters = n
        self._refresh_chapter_list()
        self.chapters_changed.emit()
        self.project_updated.emit()

    # ------------------------------------------------------------------
    # Slot handlers – Metadata section
    # ------------------------------------------------------------------

    def _on_metadata_changed(self) -> None:
        if self._updating:
            return
        m = self._project.metadata
        m.title = self._title_edit.text()
        m.subtitle = self._subtitle_edit.text()
        m.author = self._author_edit.text()
        m.co_authors = self._coauthors_edit.text()
        m.genre = self._genre_edit.text()
        m.target_audience = self._audience_combo.currentText()
        m.language = self._language_edit.text()
        m.description = self._description_edit.toPlainText()
        self.project_updated.emit()

    # ------------------------------------------------------------------
    # Slot handlers – Generation Options section
    # ------------------------------------------------------------------

    def _on_gen_options_changed(self) -> None:
        if self._updating:
            return
        gc = self._project.generation_config
        gc.include_frontmatter = self._frontmatter_check.isChecked()
        gc.include_backmatter = self._backmatter_check.isChecked()
        gc.include_toc = self._toc_check.isChecked()
        gc.auto_save = self._autosave_check.isChecked()
        gc.save_interval = self._save_interval_spin.value()
        gc.pause_between_chapters = self._pause_check.isChecked()
        self.project_updated.emit()

    # ------------------------------------------------------------------
    # Slot handlers – Outline section
    # ------------------------------------------------------------------

    def _on_outline_changed(self) -> None:
        if self._updating:
            return
        text = self._outline_edit.toPlainText()
        self._project.outline = text
        self.outline_edited.emit(text)
        self.project_updated.emit()

    def _on_edit_outline_full(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Edit Outline — Full View")
        dialog.resize(720, 560)
        layout = QVBoxLayout(dialog)

        editor = QPlainTextEdit()
        editor.setPlainText(self._outline_edit.toPlainText())
        layout.addWidget(editor)

        btn_row = QHBoxLayout()
        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("Cancel")
        btn_row.addStretch()
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        def _apply():
            self._outline_edit.setPlainText(editor.toPlainText())
            dialog.accept()

        ok_btn.clicked.connect(_apply)
        cancel_btn.clicked.connect(dialog.reject)
        dialog.exec()

    # ------------------------------------------------------------------
    # Slot handlers – Chapter List section
    # ------------------------------------------------------------------

    def _on_chapter_selected(self, row: int) -> None:
        if self._updating or row < 0:
            return
        ch = self._project.get_chapter(row)
        if ch is None:
            return
        self._updating = True
        self._ch_title_edit.setText(ch.title)
        self._ch_synopsis_edit.setPlainText(ch.synopsis)
        self._updating = False

    def _on_ch_title_edited(self, text: str) -> None:
        if self._updating:
            return
        row = self._chapter_list.currentRow()
        if row < 0:
            return
        ch = self._project.get_chapter(row)
        if ch is None:
            return
        ch.title = text
        # Update the list item display
        suffix = " (generated)" if ch.content_generated else ""
        self._chapter_list.item(row).setText(f"Ch {row + 1}: {ch.title}{suffix}")
        self.chapters_changed.emit()
        self.project_updated.emit()

    def _on_ch_synopsis_edited(self) -> None:
        if self._updating:
            return
        row = self._chapter_list.currentRow()
        if row < 0:
            return
        ch = self._project.get_chapter(row)
        if ch is None:
            return
        ch.synopsis = self._ch_synopsis_edit.toPlainText()
        self.project_updated.emit()

    def _on_add_chapter(self) -> None:
        self._project.add_chapter()
        self._refresh_chapter_list()
        # Select the newly added (last) chapter
        self._chapter_list.setCurrentRow(len(self._project.chapters) - 1)
        self.chapters_changed.emit()
        self.project_updated.emit()

    def _on_remove_chapter(self) -> None:
        row = self._chapter_list.currentRow()
        if row < 0:
            return
        self._project.remove_chapter(row)
        self._refresh_chapter_list()
        self.chapters_changed.emit()
        self.project_updated.emit()

    def _on_move_up(self) -> None:
        row = self._chapter_list.currentRow()
        if row <= 0:
            return
        chapters = self._project.chapters
        chapters[row], chapters[row - 1] = chapters[row - 1], chapters[row]
        for i, ch in enumerate(chapters):
            ch.index = i
        self._refresh_chapter_list()
        self._chapter_list.setCurrentRow(row - 1)
        self.chapters_changed.emit()
        self.project_updated.emit()

    def _on_move_down(self) -> None:
        row = self._chapter_list.currentRow()
        if row < 0 or row >= len(self._project.chapters) - 1:
            return
        chapters = self._project.chapters
        chapters[row], chapters[row + 1] = chapters[row + 1], chapters[row]
        for i, ch in enumerate(chapters):
            ch.index = i
        self._refresh_chapter_list()
        self._chapter_list.setCurrentRow(row + 1)
        self.chapters_changed.emit()
        self.project_updated.emit()