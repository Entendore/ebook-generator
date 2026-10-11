"""World Bible panel for managing characters, locations, concepts, and
other narrative-consistency entries.

The left-hand list shows all entries filtered by type; the right-hand form
lets the user view / edit a selected entry.  Two outward signals allow the
main window to react: ``bible_changed`` whenever the data is mutated, and
``request_ai_world_bible`` when the user wants the LLM to auto-populate
entries.
"""

from __future__ import annotations

import copy
import uuid
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..models.book_project import BookProject
from ..models.extended_models import WorldBible, WorldBibleEntry

# ---------------------------------------------------------------------------
# Catppuccin Mocha palette
# ---------------------------------------------------------------------------
_CTP_BG = "#1e1e2e"
_CTP_SURFACE = "#313244"
_CTP_OVERLAY = "#45475a"
_CTP_TEXT = "#cdd6f4"
_CTP_SUBTEXT = "#a6adc8"
_CTP_ACCENT = "#89b4fa"
_CTP_GREEN = "#a6e3a1"
_CTP_RED = "#f38ba8"
_CTP_YELLOW = "#f9e2af"
_CTP_MANTLE = "#181825"

# Type → display label + icon character
_TYPE_ICONS: dict[str, tuple[str, str]] = {
    "character": ("👤", "Character"),
    "location": ("📍", "Location"),
    "concept": ("💡", "Concept"),
    "item": ("🗡️", "Item"),
    "organization": ("🏛️", "Organization"),
}

_ENTRY_TYPES = ["character", "location", "concept", "item", "organization"]

_FILTER_OPTIONS = ["All", "Characters", "Locations", "Concepts", "Items", "Organizations"]
_FILTER_MAP = {
    "All": None,
    "Characters": "character",
    "Locations": "location",
    "Concepts": "concept",
    "Items": "item",
    "Organizations": "organization",
}

_PANEL_STYLE = f"""
    QWidget#worldBiblePanel {{
        background-color: {_CTP_BG};
    }}
    QComboBox {{
        background-color: {_CTP_SURFACE};
        color: {_CTP_TEXT};
        border: 1px solid {_CTP_OVERLAY};
        padding: 6px 10px;
        border-radius: 4px;
        font-size: 13px;
        min-width: 140px;
    }}
    QComboBox::drop-down {{
        border: none;
        width: 24px;
    }}
    QComboBox::down-arrow {{
        image: none;
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 6px solid {_CTP_SUBTEXT};
        margin-right: 8px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {_CTP_SURFACE};
        color: {_CTP_TEXT};
        border: 1px solid {_CTP_OVERLAY};
        selection-background-color: {_CTP_OVERLAY};
        selection-color: {_CTP_ACCENT};
    }}
    QLineEdit {{
        background-color: {_CTP_SURFACE};
        color: {_CTP_TEXT};
        border: 1px solid {_CTP_OVERLAY};
        padding: 6px 10px;
        border-radius: 4px;
        font-size: 13px;
    }}
    QLineEdit:focus {{
        border: 1px solid {_CTP_ACCENT};
    }}
    QTextEdit {{
        background-color: {_CTP_SURFACE};
        color: {_CTP_TEXT};
        border: 1px solid {_CTP_OVERLAY};
        padding: 6px 8px;
        border-radius: 4px;
        font-size: 13px;
        selection-background-color: {_CTP_OVERLAY};
    }}
    QTextEdit:focus {{
        border: 1px solid {_CTP_ACCENT};
    }}
    QListWidget {{
        background-color: {_CTP_SURFACE};
        color: {_CTP_TEXT};
        border: 1px solid {_CTP_OVERLAY};
        border-radius: 4px;
        font-size: 13px;
        padding: 4px;
        outline: none;
    }}
    QListWidget::item {{
        padding: 6px 8px;
        border-radius: 3px;
    }}
    QListWidget::item:selected {{
        background-color: {_CTP_OVERLAY};
        color: {_CTP_ACCENT};
    }}
    QListWidget::item:hover:!selected {{
        background-color: {_CTP_SURFACE};
    }}
    QSpinBox {{
        background-color: {_CTP_SURFACE};
        color: {_CTP_TEXT};
        border: 1px solid {_CTP_OVERLAY};
        padding: 6px 10px;
        border-radius: 4px;
        font-size: 13px;
        min-width: 100px;
    }}
    QSpinBox::up-button, QSpinBox::down-button {{
        background-color: {_CTP_OVERLAY};
        border: none;
        width: 20px;
    }}
    QSpinBox::up-arrow {{
        image: none;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-bottom: 5px solid {_CTP_SUBTEXT};
    }}
    QSpinBox::down-arrow {{
        image: none;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 5px solid {_CTP_SUBTEXT};
    }}
    QLabel {{
        color: {_CTP_SUBTEXT};
        font-size: 13px;
    }}
    QLabel#formLabel {{
        color: {_CTP_TEXT};
        font-weight: bold;
        font-size: 13px;
    }}
    QPushButton {{
        background-color: {_CTP_SURFACE};
        color: {_CTP_TEXT};
        border: 1px solid {_CTP_OVERLAY};
        padding: 6px 14px;
        border-radius: 4px;
        font-size: 13px;
    }}
    QPushButton:hover {{
        background-color: {_CTP_OVERLAY};
    }}
    QPushButton:pressed {{
        background-color: {_CTP_SURFACE};
    }}
    QPushButton#addBtn {{
        color: {_CTP_GREEN};
        border: 1px solid {_CTP_GREEN};
        font-weight: bold;
    }}
    QPushButton#addBtn:hover {{
        background-color: {_CTP_OVERLAY};
    }}
    QPushButton#aiBtn {{
        color: {_CTP_ACCENT};
        border: 1px solid {_CTP_ACCENT};
        font-weight: bold;
    }}
    QPushButton#aiBtn:hover {{
        background-color: {_CTP_OVERLAY};
    }}
    QPushButton#injectBtn {{
        color: {_CTP_YELLOW};
        border: 1px solid {_CTP_YELLOW};
        font-weight: bold;
    }}
    QPushButton#injectBtn:hover {{
        background-color: {_CTP_OVERLAY};
    }}
    QPushButton#saveBtn {{
        color: {_CTP_GREEN};
        border: 1px solid {_CTP_GREEN};
        font-weight: bold;
    }}
    QPushButton#saveBtn:hover {{
        background-color: {_CTP_OVERLAY};
    }}
    QPushButton#deleteBtn {{
        color: {_CTP_RED};
        border: 1px solid {_CTP_RED};
        font-weight: bold;
    }}
    QPushButton#deleteBtn:hover {{
        background-color: {_CTP_OVERLAY};
    }}
    QPushButton#duplicateBtn {{
        color: {_CTP_ACCENT};
        border: 1px solid {_CTP_ACCENT};
        font-weight: bold;
    }}
    QPushButton#duplicateBtn:hover {{
        background-color: {_CTP_OVERLAY};
    }}
    QPushButton#addAttrBtn {{
        color: {_CTP_GREEN};
        border: 1px solid {_CTP_GREEN};
        padding: 4px 10px;
        font-size: 12px;
    }}
    QPushButton#removeAttrBtn {{
        color: {_CTP_RED};
        border: 1px solid {_CTP_RED};
        padding: 4px 10px;
        font-size: 12px;
    }}
    QSplitter::handle {{
        background-color: {_CTP_OVERLAY};
        width: 2px;
    }}
    QFormLayout {{
        spacing: 8px;
    }}
    QDialog {{
        background-color: {_CTP_BG};
        color: {_CTP_TEXT};
    }}
"""


class WorldBiblePanel(QWidget):
    """Panel for managing the World Bible of a book project."""

    bible_changed = Signal()
    request_ai_world_bible = Signal(str)

    def __init__(self, project: BookProject) -> None:
        super().__init__()
        self.setObjectName("worldBiblePanel")
        self._project: Optional[BookProject] = project
        self._current_entry_id: Optional[str] = None

        self._build_ui()
        self.refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_project(self, project: BookProject) -> None:
        """Swap the underlying project and refresh."""
        self._project = project
        self._current_entry_id = None
        self.refresh()

    def refresh(self) -> None:
        """Repopulate the entry list from the project's world bible."""
        self._entry_list.blockSignals(True)
        self._entry_list.clear()

        if self._project is None or self._project.world_bible is None:
            self._entry_list.blockSignals(False)
            self._clear_editor()
            return

        bible: WorldBible = self._project.world_bible  # type: ignore[assignment]
        filter_type = _FILTER_MAP.get(self._filter_combo.currentText())

        for entry in bible.entries:
            if filter_type is not None and entry.entry_type != filter_type:
                continue
            icon, label = _TYPE_ICONS.get(entry.entry_type, ("📝", entry.entry_type))
            item_text = f"{icon} {entry.name or 'Untitled'} ({label})"
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, entry.id)
            self._entry_list.addItem(item)

        # Re-select if the current entry is still visible
        if self._current_entry_id is not None:
            for i in range(self._entry_list.count()):
                item = self._entry_list.item(i)
                if item.data(Qt.ItemDataRole.UserRole) == self._current_entry_id:
                    self._entry_list.setCurrentRow(i)
                    self._entry_list.blockSignals(False)
                    return

        self._entry_list.blockSignals(False)
        self._clear_editor()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.setStyleSheet(_PANEL_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # --- Top bar ---
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        self._filter_combo = QComboBox()
        self._filter_combo.addItems(_FILTER_OPTIONS)
        self._filter_combo.setMinimumWidth(150)
        self._filter_combo.currentTextChanged.connect(lambda _: self.refresh())
        top_bar.addWidget(self._filter_combo)

        self._add_btn = QPushButton("Add Entry")
        self._add_btn.setObjectName("addBtn")
        self._add_btn.clicked.connect(self._on_add_entry)
        top_bar.addWidget(self._add_btn)

        self._ai_btn = QPushButton("AI Generate Entries")
        self._ai_btn.setObjectName("aiBtn")
        self._ai_btn.clicked.connect(self._on_ai_generate)
        top_bar.addWidget(self._ai_btn)

        self._inject_btn = QPushButton("Inject into Prompt")
        self._inject_btn.setObjectName("injectBtn")
        self._inject_btn.clicked.connect(self._on_inject)
        top_bar.addWidget(self._inject_btn)

        top_bar.addStretch()
        root.addLayout(top_bar)

        # --- Splitter: list (left) | editor (right) ---
        self._splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left — entry list
        self._entry_list = QListWidget()
        self._entry_list.currentRowChanged.connect(self._on_entry_selected)
        self._entry_list.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        self._splitter.addWidget(self._entry_list)

        # Right — editor form in a scrollable wrapper
        editor_container = QWidget()
        editor_layout = QVBoxLayout(editor_container)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)

        form_widget = QWidget()
        self._form_layout = QFormLayout(form_widget)
        self._form_layout.setContentsMargins(8, 4, 8, 4)
        self._form_layout.setSpacing(8)
        self._form_layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )

        # Name
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Entry name…")
        name_label = QLabel("Name")
        name_label.setObjectName("formLabel")
        self._form_layout.addRow(name_label, self._name_edit)

        # Type
        self._type_combo = QComboBox()
        for t in _ENTRY_TYPES:
            icon, label = _TYPE_ICONS.get(t, ("📝", t))
            self._type_combo.addItem(f"{icon} {label}", t)
        type_label = QLabel("Type")
        type_label.setObjectName("formLabel")
        self._form_layout.addRow(type_label, self._type_combo)

        # Aliases
        self._aliases_edit = QLineEdit()
        self._aliases_edit.setPlaceholderText("comma-separated aliases…")
        aliases_label = QLabel("Aliases")
        aliases_label.setObjectName("formLabel")
        self._form_layout.addRow(aliases_label, self._aliases_edit)

        # Description
        self._desc_edit = QTextEdit()
        self._desc_edit.setPlaceholderText("Describe this entry…")
        self._desc_edit.setFixedHeight(72)
        desc_label = QLabel("Description")
        desc_label.setObjectName("formLabel")
        self._form_layout.addRow(desc_label, self._desc_edit)

        # Attributes — dynamic key-value rows
        attr_header_layout = QHBoxLayout()
        attr_title = QLabel("Attributes")
        attr_title.setObjectName("formLabel")
        attr_header_layout.addWidget(attr_title)
        attr_header_layout.addStretch()

        self._add_attr_btn = QPushButton("+")
        self._add_attr_btn.setObjectName("addAttrBtn")
        self._add_attr_btn.setFixedSize(28, 28)
        self._add_attr_btn.setToolTip("Add attribute row")
        self._add_attr_btn.clicked.connect(self._add_attribute_row)
        attr_header_layout.addWidget(self._add_attr_btn)

        self._form_layout.addRow(attr_header_layout)

        self._attr_container = QVBoxLayout()
        self._attr_container.setSpacing(4)
        self._attr_rows: list[tuple[QLineEdit, QLineEdit, QPushButton]] = []
        self._form_layout.addRow(self._attr_container)

        # Notes
        self._notes_edit = QTextEdit()
        self._notes_edit.setPlaceholderText("Additional notes…")
        self._notes_edit.setFixedHeight(48)
        notes_label = QLabel("Notes")
        notes_label.setObjectName("formLabel")
        self._form_layout.addRow(notes_label, self._notes_edit)

        # First Appearance Chapter
        self._chapter_spin = QSpinBox()
        self._chapter_spin.setRange(-1, 999)
        self._chapter_spin.setValue(-1)
        self._chapter_spin.setSpecialValueText("N/A")
        self._chapter_spin.setToolTip("Chapter index where this entry first appears (-1 = not set)")
        chapter_label = QLabel("First Appearance")
        chapter_label.setObjectName("formLabel")
        self._form_layout.addRow(chapter_label, self._chapter_spin)

        editor_layout.addWidget(form_widget)
        editor_layout.addStretch()
        self._splitter.addWidget(editor_container)

        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 2)
        self._splitter.setSizes([250, 500])

        root.addWidget(self._splitter, stretch=1)

        # --- Bottom action bar ---
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(8)

        self._save_btn = QPushButton("Save Entry")
        self._save_btn.setObjectName("saveBtn")
        self._save_btn.clicked.connect(self._on_save_entry)
        bottom_bar.addWidget(self._save_btn)

        self._delete_btn = QPushButton("Delete Entry")
        self._delete_btn.setObjectName("deleteBtn")
        self._delete_btn.clicked.connect(self._on_delete_entry)
        bottom_bar.addWidget(self._delete_btn)

        self._duplicate_btn = QPushButton("Duplicate Entry")
        self._duplicate_btn.setObjectName("duplicateBtn")
        self._duplicate_btn.clicked.connect(self._on_duplicate_entry)
        bottom_bar.addWidget(self._duplicate_btn)

        bottom_bar.addStretch()

        self._count_label = QLabel("0 entries")
        self._count_label.setObjectName("formLabel")
        bottom_bar.addWidget(self._count_label)

        root.addLayout(bottom_bar)

    # ------------------------------------------------------------------
    # Attribute rows
    # ------------------------------------------------------------------

    def _add_attribute_row(
        self, key: str = "", value: str = ""
    ) -> tuple[QLineEdit, QLineEdit, QPushButton]:
        """Append a key-value attribute row to the form and return widgets."""
        row_layout = QHBoxLayout()
        row_layout.setSpacing(4)

        key_edit = QLineEdit(key)
        key_edit.setPlaceholderText("Key")
        key_edit.setMaximumWidth(160)
        value_edit = QLineEdit(value)
        value_edit.setPlaceholderText("Value")

        remove_btn = QPushButton("−")
        remove_btn.setObjectName("removeAttrBtn")
        remove_btn.setFixedSize(28, 28)
        remove_btn.setToolTip("Remove this attribute")

        row_layout.addWidget(key_edit)
        row_layout.addWidget(value_edit, stretch=1)
        row_layout.addWidget(remove_btn)

        container = QWidget()
        container.setLayout(row_layout)
        container.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._attr_container.addWidget(container)

        pair = (key_edit, value_edit, remove_btn)
        self._attr_rows.append(pair)
        remove_btn.clicked.connect(lambda _, p=pair, c=container: self._remove_attribute_row(p, c))
        return pair

    def _remove_attribute_row(
        self, pair: tuple[QLineEdit, QLineEdit, QPushButton], container: QWidget
    ) -> None:
        """Remove a single attribute row from the form."""
        if pair in self._attr_rows:
            self._attr_rows.remove(pair)
        self._attr_container.removeWidget(container)
        container.deleteLater()

    def _clear_attribute_rows(self) -> None:
        """Remove all attribute rows from the form."""
        for pair, container in zip(
            list(self._attr_rows),
            [w.parent() or w for w, _, _ in self._attr_rows],
        ):
            self._attr_container.removeWidget(container)
            container.deleteLater()
        self._attr_rows.clear()

    def _collect_attributes(self) -> dict[str, str]:
        """Gather current key-value pairs from the attribute rows."""
        attrs: dict[str, str] = {}
        for key_edit, value_edit, _ in self._attr_rows:
            k = key_edit.text().strip()
            v = value_edit.text().strip()
            if k:
                attrs[k] = v
        return attrs

    # ------------------------------------------------------------------
    # Slots — list interactions
    # ------------------------------------------------------------------

    def _on_entry_selected(self, row: int) -> None:
        """Load the selected entry into the editor form."""
        if row < 0:
            self._current_entry_id = None
            self._clear_editor()
            return

        item = self._entry_list.item(row)
        if item is None:
            return

        entry_id = item.data(Qt.ItemDataRole.UserRole)
        self._load_entry(entry_id)

    # ------------------------------------------------------------------
    # Slots — button actions
    # ------------------------------------------------------------------

    def _on_add_entry(self) -> None:
        """Create a new blank entry and select it."""
        if self._project is None or self._project.world_bible is None:
            return

        entry = WorldBibleEntry(
            entry_type="character",
            name="New Entry",
        )
        self._project.world_bible.add_entry(entry)
        self._current_entry_id = entry.id
        self.refresh()
        # Select the newly added entry
        for i in range(self._entry_list.count()):
            it = self._entry_list.item(i)
            if it.data(Qt.ItemDataRole.UserRole) == entry.id:
                self._entry_list.setCurrentRow(i)
                break
        self._name_edit.selectAll()
        self._name_edit.setFocus()
        self.bible_changed.emit()

    def _on_save_entry(self) -> None:
        """Persist editor values back to the world bible entry."""
        if self._project is None or self._project.world_bible is None:
            return
        if self._current_entry_id is None:
            return

        bible: WorldBible = self._project.world_bible  # type: ignore[assignment]
        entry = bible.get_entry(self._current_entry_id)
        if entry is None:
            return

        entry.name = self._name_edit.text().strip() or "Untitled"
        entry.entry_type = self._type_combo.currentData()
        entry.aliases = [
            a.strip()
            for a in self._aliases_edit.text().split(",")
            if a.strip()
        ]
        entry.description = self._desc_edit.toPlainText().strip()
        entry.attributes = self._collect_attributes()
        entry.notes = self._notes_edit.toPlainText().strip()
        entry.first_appearance_chapter = self._chapter_spin.value()

        self.refresh()
        self.bible_changed.emit()

    def _on_delete_entry(self) -> None:
        """Delete the currently selected entry after confirmation."""
        if self._project is None or self._project.world_bible is None:
            return
        if self._current_entry_id is None:
            return

        bible: WorldBible = self._project.world_bible  # type: ignore[assignment]
        entry = bible.get_entry(self._current_entry_id)
        if entry is None:
            return

        reply = QMessageBox.question(
            self,
            "Delete Entry",
            f"Delete \"{entry.name}\" from the World Bible?\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        bible.remove_entry(self._current_entry_id)
        self._current_entry_id = None
        self.refresh()
        self.bible_changed.emit()

    def _on_duplicate_entry(self) -> None:
        """Duplicate the currently selected entry with a new ID."""
        if self._project is None or self._project.world_bible is None:
            return
        if self._current_entry_id is None:
            return

        bible: WorldBible = self._project.world_bible  # type: ignore[assignment]
        entry = bible.get_entry(self._current_entry_id)
        if entry is None:
            return

        # Save any pending edits first
        self._on_save_entry()

        new_entry = copy.deepcopy(entry)
        new_entry.id = str(uuid.uuid4())[:8]
        new_entry.name = f"{entry.name} (Copy)"
        bible.add_entry(new_entry)
        self._current_entry_id = new_entry.id
        self.refresh()

        # Select the duplicated entry
        for i in range(self._entry_list.count()):
            it = self._entry_list.item(i)
            if it.data(Qt.ItemDataRole.UserRole) == new_entry.id:
                self._entry_list.setCurrentRow(i)
                break
        self.bible_changed.emit()

    def _on_ai_generate(self) -> None:
        """Show a dialog prompting the user for a world description, then
        emit ``request_ai_world_bible`` with the text."""
        dialog = QDialog(self)
        dialog.setWindowTitle("AI Generate World Bible Entries")
        dialog.setMinimumSize(520, 380)
        dialog.setStyleSheet(_PANEL_STYLE)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        prompt_label = QLabel(
            "Describe the characters and world of your book.\n"
            "The AI will generate World Bible entries from this description."
        )
        prompt_label.setWordWrap(True)
        prompt_label.setStyleSheet(f"color: {_CTP_TEXT}; font-size: 14px;")
        layout.addWidget(prompt_label)

        desc_edit = QTextEdit()
        desc_edit.setPlaceholderText(
            "e.g. A medieval fantasy world with three kingdoms, "
            "a young knight named Aldric who wields a cursed sword, "
            "a secretive guild of alchemists, the capital city of Thornwall…"
        )
        layout.addWidget(desc_edit, stretch=1)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {_CTP_SURFACE}; color: {_CTP_TEXT};"
            f"  border: 1px solid {_CTP_OVERLAY}; padding: 6px 18px;"
            f"  border-radius: 4px; font-size: 13px;"
            f"}}"
            f"QPushButton:hover {{ background-color: {_CTP_OVERLAY}; }}"
        )
        btn_box.accepted.connect(dialog.accept)
        btn_box.rejected.connect(dialog.reject)
        layout.addWidget(btn_box)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            text = desc_edit.toPlainText().strip()
            if text:
                self.request_ai_world_bible.emit(text)

    def _on_inject(self) -> None:
        """Build world-bible context text and copy it to the clipboard."""
        if self._project is None or self._project.world_bible is None:
            QMessageBox.information(
                self, "Inject", "No world bible data available to inject."
            )
            return

        bible: WorldBible = self._project.world_bible  # type: ignore[assignment]
        context = bible.to_context_text()

        if not context.strip():
            QMessageBox.information(
                self, "Inject", "The world bible is empty — nothing to inject."
            )
            return

        clipboard = self._find_clipboard()
        clipboard.setText(context)
        QMessageBox.information(
            self,
            "Injected",
            f"World Bible context ({len(context):,} chars) copied to clipboard.\n\n"
            "You can now paste it into any prompt.",
        )

    # ------------------------------------------------------------------
    # Internal — load / clear editor
    # ------------------------------------------------------------------

    def _load_entry(self, entry_id: str) -> None:
        """Populate the editor form from a WorldBibleEntry."""
        if self._project is None or self._project.world_bible is None:
            return

        bible: WorldBible = self._project.world_bible  # type: ignore[assignment]
        entry = bible.get_entry(entry_id)
        if entry is None:
            self._clear_editor()
            return

        self._current_entry_id = entry.id

        self._name_edit.setText(entry.name)
        # Set type combo
        type_index = self._type_combo.findData(entry.entry_type)
        if type_index >= 0:
            self._type_combo.setCurrentIndex(type_index)
        self._aliases_edit.setText(", ".join(entry.aliases))
        self._desc_edit.setPlainText(entry.description)
        self._notes_edit.setPlainText(entry.notes)
        self._chapter_spin.setValue(entry.first_appearance_chapter)

        # Attributes
        self._clear_attribute_rows()
        for k, v in entry.attributes.items():
            self._add_attribute_row(k, v)

        self._update_count_label()

    def _clear_editor(self) -> None:
        """Reset all editor widgets to their default state."""
        self._name_edit.clear()
        self._type_combo.setCurrentIndex(0)
        self._aliases_edit.clear()
        self._desc_edit.clear()
        self._notes_edit.clear()
        self._chapter_spin.setValue(-1)
        self._clear_attribute_rows()
        self._update_count_label()

    def _update_count_label(self) -> None:
        """Update the entry count display."""
        if self._project is None or self._project.world_bible is None:
            self._count_label.setText("0 entries")
            return
        bible: WorldBible = self._project.world_bible  # type: ignore[assignment]
        n = len(bible.entries)
        self._count_label.setText(f"{n} entr{'y' if n == 1 else 'ies'}")

    # ------------------------------------------------------------------
    # Internal — helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_clipboard():
        """Return the QApplication clipboard (avoids direct QApplication import
        issues at module level in some environments)."""
        from PySide6.QtGui import QGuiApplication
        return QGuiApplication.clipboard()