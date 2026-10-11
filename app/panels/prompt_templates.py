"""Panel widget for managing prompt templates."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..models.book_project import BookProject, EBOOK_TYPE_LABELS, EbookType, PromptTemplate

# ---------------------------------------------------------------------------
# Catppuccin Mocha dark-theme stylesheet
# ---------------------------------------------------------------------------
_DARK_STYLE = """
QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: "Segoe UI", "Helvetica Neue", sans-serif;
    font-size: 13px;
}
QComboBox, QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 4px 8px;
    selection-background-color: #89b4fa;
    selection-color: #1e1e2e;
}
QComboBox::drop-down {
    border: none;
    background: #45475a;
    width: 20px;
    border-top-right-radius: 4px;
    border-bottom-right-radius: 4px;
}
QComboBox::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #cdd6f4;
    margin-right: 6px;
}
QComboBox QAbstractItemView {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    selection-background-color: #89b4fa;
    selection-color: #1e1e2e;
}
QTextEdit {
    border: 1px solid #45475a;
}
QPushButton {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 6px 14px;
}
QPushButton:hover {
    background-color: #45475a;
    border-color: #89b4fa;
}
QPushButton:pressed {
    background-color: #585b70;
}
QGroupBox {
    border: 1px solid #45475a;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 14px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #89b4fa;
}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    background-color: #45475a;
    border: none;
    width: 16px;
}
QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {
    background-color: #585b70;
}
QScrollBar:vertical {
    background: #1e1e2e;
    width: 10px;
    border: none;
}
QScrollBar::handle:vertical {
    background: #45475a;
    min-height: 30px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #585b70;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    background: #1e1e2e;
    height: 10px;
    border: none;
}
QScrollBar::handle:horizontal {
    background: #45475a;
    min-width: 30px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal:hover {
    background: #585b70;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}
"""

CATEGORIES = ["outline", "chapter", "frontmatter", "backmatter", "custom"]


class PromptTemplatePanel(QWidget):
    """Panel for creating, editing, and managing prompt templates."""

    def __init__(self, project: BookProject, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project = project
        self._block_populate = False
        self._setup_ui()
        self.refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_project(self, project: BookProject) -> None:
        self._project = project
        self.refresh()

    def refresh(self) -> None:
        self._populate_template_combo()
        if self._project.prompt_templates:
            self._template_combo.setCurrentIndex(0)
            self._load_template_into_form(0)
        else:
            self._clear_form()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        self.setStyleSheet(_DARK_STYLE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # --- Top bar: combo + action buttons ---
        top_layout = QHBoxLayout()
        top_layout.setSpacing(8)

        self._template_combo = QComboBox()
        self._template_combo.setMinimumWidth(200)
        self._template_combo.currentIndexChanged.connect(self._on_template_selected)
        top_layout.addWidget(self._template_combo, 1)

        btn_new = QPushButton("New Template")
        btn_new.clicked.connect(self._on_new_template)
        top_layout.addWidget(btn_new)

        btn_delete = QPushButton("Delete Template")
        btn_delete.clicked.connect(self._on_delete_template)
        top_layout.addWidget(btn_delete)

        btn_duplicate = QPushButton("Duplicate Template")
        btn_duplicate.clicked.connect(self._on_duplicate_template)
        top_layout.addWidget(btn_duplicate)

        layout.addLayout(top_layout)

        # --- Main form ---
        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)

        self._name_edit = QLineEdit()
        form.addRow("Template Name:", self._name_edit)

        self._desc_edit = QLineEdit()
        form.addRow("Description:", self._desc_edit)

        self._category_combo = QComboBox()
        self._category_combo.addItems(CATEGORIES)
        form.addRow("Category:", self._category_combo)

        self._ebook_type_combo = QComboBox()
        self._ebook_type_combo.addItem("general", "general")
        for et, label in EBOOK_TYPE_LABELS.items():
            self._ebook_type_combo.addItem(label, et.value)
        form.addRow("Ebook Type:", self._ebook_type_combo)

        self._system_prompt_edit = QTextEdit()
        self._system_prompt_edit.setMinimumHeight(100)
        self._system_prompt_edit.setAcceptRichText(False)
        form.addRow("System Prompt:", self._system_prompt_edit)

        self._user_prompt_edit = QTextEdit()
        self._user_prompt_edit.setMinimumHeight(120)
        self._user_prompt_edit.setAcceptRichText(False)
        form.addRow("User Prompt Template:", self._user_prompt_edit)

        self._variables_edit = QLineEdit()
        self._variables_edit.setPlaceholderText("e.g. title,author,chapter_title")
        form.addRow("Variables:", self._variables_edit)

        layout.addLayout(form)

        # --- Sampling Parameters group ---
        sampling_group = QGroupBox("Sampling Parameters")
        sampling_layout = QFormLayout()
        sampling_layout.setHorizontalSpacing(14)
        sampling_layout.setVerticalSpacing(8)

        self._temperature_spin = QDoubleSpinBox()
        self._temperature_spin.setRange(0.0, 2.0)
        self._temperature_spin.setSingleStep(0.1)
        self._temperature_spin.setValue(0.7)
        self._temperature_spin.setDecimals(2)
        sampling_layout.addRow("Temperature:", self._temperature_spin)

        self._top_p_spin = QDoubleSpinBox()
        self._top_p_spin.setRange(0.0, 1.0)
        self._top_p_spin.setSingleStep(0.05)
        self._top_p_spin.setValue(0.9)
        self._top_p_spin.setDecimals(2)
        sampling_layout.addRow("Top P:", self._top_p_spin)

        self._top_k_spin = QSpinBox()
        self._top_k_spin.setRange(0, 200)
        self._top_k_spin.setValue(40)
        sampling_layout.addRow("Top K:", self._top_k_spin)

        self._max_tokens_spin = QSpinBox()
        self._max_tokens_spin.setRange(256, 32768)
        self._max_tokens_spin.setSingleStep(256)
        self._max_tokens_spin.setValue(4096)
        sampling_layout.addRow("Max Tokens:", self._max_tokens_spin)

        self._repeat_penalty_spin = QDoubleSpinBox()
        self._repeat_penalty_spin.setRange(0.5, 2.0)
        self._repeat_penalty_spin.setSingleStep(0.05)
        self._repeat_penalty_spin.setValue(1.1)
        self._repeat_penalty_spin.setDecimals(2)
        sampling_layout.addRow("Repeat Penalty:", self._repeat_penalty_spin)

        sampling_group.setLayout(sampling_layout)
        layout.addWidget(sampling_group)

        # --- Bottom buttons ---
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(10)

        self._save_btn = QPushButton("Save Template")
        self._save_btn.clicked.connect(self._on_save_template)
        bottom_layout.addWidget(self._save_btn)

        self._defaults_btn = QPushButton("Load Default Templates")
        self._defaults_btn.clicked.connect(self._on_load_defaults)
        bottom_layout.addWidget(self._defaults_btn)

        bottom_layout.addStretch()
        layout.addLayout(bottom_layout)

    # ------------------------------------------------------------------
    # Combo helpers
    # ------------------------------------------------------------------

    def _populate_template_combo(self) -> None:
        self._block_populate = True
        self._template_combo.clear()
        for pt in self._project.prompt_templates:
            self._template_combo.addItem(pt.name, pt.id)
        self._block_populate = False

    def _current_template(self) -> PromptTemplate | None:
        idx = self._template_combo.currentIndex()
        if 0 <= idx < len(self._project.prompt_templates):
            return self._project.prompt_templates[idx]
        return None

    # ------------------------------------------------------------------
    # Form load / save
    # ------------------------------------------------------------------

    def _clear_form(self) -> None:
        self._name_edit.clear()
        self._desc_edit.clear()
        self._category_combo.setCurrentIndex(0)
        self._ebook_type_combo.setCurrentIndex(0)
        self._system_prompt_edit.clear()
        self._user_prompt_edit.clear()
        self._variables_edit.clear()
        self._temperature_spin.setValue(0.7)
        self._top_p_spin.setValue(0.9)
        self._top_k_spin.setValue(40)
        self._max_tokens_spin.setValue(4096)
        self._repeat_penalty_spin.setValue(1.1)

    def _load_template_into_form(self, index: int) -> None:
        if self._block_populate:
            return
        if not (0 <= index < len(self._project.prompt_templates)):
            self._clear_form()
            return
        pt = self._project.prompt_templates[index]

        self._name_edit.setText(pt.name)
        self._desc_edit.setText(pt.description)

        cat_idx = self._category_combo.findText(pt.category)
        self._category_combo.setCurrentIndex(max(cat_idx, 0))

        et_idx = self._ebook_type_combo.findData(pt.ebook_type)
        if et_idx < 0:
            et_idx = 0
        self._ebook_type_combo.setCurrentIndex(et_idx)

        self._system_prompt_edit.setPlainText(pt.system_prompt)
        self._user_prompt_edit.setPlainText(pt.user_prompt_template)

        self._variables_edit.setText(", ".join(pt.variables.keys()))

        self._temperature_spin.setValue(pt.temperature)
        self._top_p_spin.setValue(pt.top_p)
        self._top_k_spin.setValue(pt.top_k)
        self._max_tokens_spin.setValue(pt.max_tokens)
        self._repeat_penalty_spin.setValue(pt.repeat_penalty)

    def _save_form_to_template(self) -> None:
        pt = self._current_template()
        if pt is None:
            return

        pt.name = self._name_edit.text().strip() or "Untitled Template"
        pt.description = self._desc_edit.text().strip()
        pt.category = self._category_combo.currentText()
        pt.ebook_type = self._ebook_type_combo.currentData()
        if pt.ebook_type is None:
            pt.ebook_type = "general"
        pt.system_prompt = self._system_prompt_edit.toPlainText()
        pt.user_prompt_template = self._user_prompt_edit.toPlainText()

        var_names = [v.strip() for v in self._variables_edit.text().split(",") if v.strip()]
        old_vars = pt.variables
        pt.variables = {v: old_vars.get(v, "") for v in var_names}

        pt.temperature = self._temperature_spin.value()
        pt.top_p = self._top_p_spin.value()
        pt.top_k = self._top_k_spin.value()
        pt.max_tokens = self._max_tokens_spin.value()
        pt.repeat_penalty = self._repeat_penalty_spin.value()

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_template_selected(self, index: int) -> None:
        self._load_template_into_form(index)

    def _on_new_template(self) -> None:
        pt = PromptTemplate(name="New Template")
        self._project.prompt_templates.append(pt)
        self.refresh()
        self._template_combo.setCurrentIndex(len(self._project.prompt_templates) - 1)
        self._name_edit.setFocus()
        self._name_edit.selectAll()

    def _on_delete_template(self) -> None:
        pt = self._current_template()
        if pt is None:
            return
        reply = QMessageBox.question(
            self,
            "Delete Template",
            f"Are you sure you want to delete \"{pt.name}\"?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._project.prompt_templates.remove(pt)
            self.refresh()

    def _on_duplicate_template(self) -> None:
        pt = self._current_template()
        if pt is None:
            return
        import copy
        new_pt = copy.deepcopy(pt)
        new_pt.name = f"{pt.name} (Copy)"
        self._project.prompt_templates.append(new_pt)
        self.refresh()
        self._template_combo.setCurrentIndex(len(self._project.prompt_templates) - 1)

    def _on_save_template(self) -> None:
        pt = self._current_template()
        if pt is None:
            QMessageBox.warning(self, "No Template", "No template selected to save.")
            return
        self._save_form_to_template()
        # Refresh combo text in case name changed
        self._block_populate = True
        idx = self._template_combo.currentIndex()
        self._template_combo.setItemText(idx, pt.name)
        self._block_populate = False

    def _on_load_defaults(self) -> None:
        """Create default templates for each category."""
        # Check if defaults already exist and ask
        existing_names = {pt.name for pt in self._project.prompt_templates}
        defaults = self._create_default_templates()
        overlap = [d for d in defaults if d.name in existing_names]
        if overlap:
            names = ", ".join(d.name for d in overlap)
            reply = QMessageBox.question(
                self,
                "Overwrite Defaults",
                f"The following templates already exist:\n{names}\n\nOverwrite them?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
            # Remove old versions
            for d in defaults:
                self._project.prompt_templates = [
                    pt for pt in self._project.prompt_templates if pt.name != d.name
                ]

        self._project.prompt_templates.extend(defaults)
        self.refresh()

    # ------------------------------------------------------------------
    # Default template factory
    # ------------------------------------------------------------------

    @staticmethod
    def _create_default_templates() -> list[PromptTemplate]:
        templates: list[PromptTemplate] = []

        # -- Default Outline --
        templates.append(PromptTemplate(
            name="Default Outline",
            description="Generate a structured book outline from title and author info.",
            category="outline",
            ebook_type="general",
            system_prompt=(
                "You are an expert book outline writer. "
                "Create a detailed, well-structured outline for the book described. "
                "Include chapter titles, brief synopses, and a logical flow."
            ),
            user_prompt_template=(
                "Create a detailed outline for the following book:\n\n"
                "Title: {{title}}\n"
                "Author: {{author}}\n"
                "Genre: {{genre}}\n"
                "Description: {{description}}\n\n"
                "Target: approximately {{total_chapters}} chapters.\n"
                "Provide a title and a 1-2 sentence synopsis for each chapter."
            ),
            variables={"title": "", "author": "", "genre": "", "description": "", "total_chapters": ""},
            temperature=0.7,
            top_p=0.9,
            top_k=40,
            max_tokens=4096,
            repeat_penalty=1.1,
        ))

        # -- Default Chapter --
        templates.append(PromptTemplate(
            name="Default Chapter",
            description="Generate a single book chapter from title, synopsis, and context.",
            category="chapter",
            ebook_type="general",
            system_prompt=(
                "You are an expert book writer. "
                "Write engaging, well-crafted prose that fits the chapter synopsis. "
                "Maintain consistent tone and style throughout."
            ),
            user_prompt_template=(
                "Write chapter {{chapter_index}} of the book \"{{title}}\" by {{author}}.\n\n"
                "Chapter Title: {{chapter_title}}\n"
                "Synopsis: {{chapter_synopsis}}\n\n"
                "Target word count: approximately {{target_words}} words.\n\n"
                "Write the full chapter content now."
            ),
            variables={
                "title": "", "author": "", "chapter_index": "",
                "chapter_title": "", "chapter_synopsis": "", "target_words": "",
            },
            temperature=0.7,
            top_p=0.9,
            top_k=40,
            max_tokens=8192,
            repeat_penalty=1.1,
        ))

        # -- Default Frontmatter --
        templates.append(PromptTemplate(
            name="Default Frontmatter",
            description="Generate front matter including title page, copyright, and dedication.",
            category="frontmatter",
            ebook_type="general",
            system_prompt=(
                "You are a professional book formatter. "
                "Generate properly formatted front matter for the book, "
                "including title page, copyright notice, and dedication if provided."
            ),
            user_prompt_template=(
                "Generate the front matter for the following book:\n\n"
                "Title: {{title}}\n"
                "Author: {{author}}\n"
                "Year: {{year}}\n"
                "Publisher: {{publisher}}\n"
                "Dedication: {{dedication}}\n"
                "Copyright Notice: {{copyright_notice}}\n\n"
                "Format in Markdown with appropriate headers."
            ),
            variables={
                "title": "", "author": "", "year": "",
                "publisher": "", "dedication": "", "copyright_notice": "",
            },
            temperature=0.5,
            top_p=0.9,
            top_k=40,
            max_tokens=2048,
            repeat_penalty=1.1,
        ))

        # -- Default Backmatter --
        templates.append(PromptTemplate(
            name="Default Backmatter",
            description="Generate back matter including about the author and acknowledgments.",
            category="backmatter",
            ebook_type="general",
            system_prompt=(
                "You are a professional book formatter. "
                "Generate well-crafted back matter for the book, "
                "including an about-the-author section and acknowledgments."
            ),
            user_prompt_template=(
                "Generate the back matter for the book \"{{title}}\" by {{author}}.\n\n"
                "Include the following sections:\n"
                "- About the Author (for {{author}})\n"
                "- Acknowledgments\n\n"
                "Format in Markdown with appropriate headers."
            ),
            variables={"title": "", "author": ""},
            temperature=0.6,
            top_p=0.9,
            top_k=40,
            max_tokens=2048,
            repeat_penalty=1.1,
        ))

        return templates