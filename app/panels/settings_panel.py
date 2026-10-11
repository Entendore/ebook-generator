"""Settings panel for application-wide configuration, model defaults, and recent projects."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..models.extended_models import AppSettings, BUILT_IN_TEMPLATES

# Catppuccin Mocha palette
_C = {
    "bg": "#1e1e2e",
    "text": "#cdd6f4",
    "accent": "#89b4fa",
    "surface": "#313244",
    "overlay": "#45475a",
    "green": "#a6e3a1",
    "red": "#f38ba8",
    "subtext": "#a6adc8",
}

_DARK_STYLE = f"""
QWidget {{
    background-color: {_C['bg']};
    color: {_C['text']};
    font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
}}

QTabWidget::pane {{
    border: 1px solid {_C['overlay']};
    border-radius: 6px;
    background: {_C['bg']};
    padding: 4px;
}}

QTabBar::tab {{
    background: {_C['surface']};
    color: {_C['subtext']};
    padding: 8px 18px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    border: 1px solid {_C['overlay']};
    border-bottom: none;
}}

QTabBar::tab:selected {{
    background: {_C['bg']};
    color: {_C['accent']};
    border-bottom: 2px solid {_C['accent']};
}}

QTabBar::tab:hover:!selected {{
    background: {_C['overlay']};
    color: {_C['text']};
}}

QGroupBox {{
    border: 1px solid {_C['overlay']};
    border-radius: 6px;
    margin-top: 14px;
    padding-top: 18px;
    font-weight: bold;
    color: {_C['accent']};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {_C['surface']};
    color: {_C['text']};
    border: 1px solid {_C['overlay']};
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 22px;
}}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {_C['accent']};
}}

QComboBox::drop-down {{
    border: none;
    width: 24px;
}}

QComboBox::down-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {_C['subtext']};
    margin-right: 6px;
}}

QComboBox QAbstractItemView {{
    background: {_C['surface']};
    color: {_C['text']};
    border: 1px solid {_C['overlay']};
    selection-background-color: {_C['overlay']};
    selection-color: {_C['accent']};
}}

QPushButton {{
    background: {_C['surface']};
    color: {_C['text']};
    border: 1px solid {_C['overlay']};
    border-radius: 4px;
    padding: 6px 14px;
    min-height: 22px;
}}

QPushButton:hover {{
    background: {_C['overlay']};
    border-color: {_C['accent']};
    color: {_C['accent']};
}}

QPushButton:pressed {{
    background: {_C['accent']};
    color: {_C['bg']};
}}

QListWidget {{
    background: {_C['surface']};
    color: {_C['text']};
    border: 1px solid {_C['overlay']};
    border-radius: 4px;
    padding: 2px;
    outline: none;
}}

QListWidget::item {{
    padding: 5px 8px;
    border-radius: 3px;
}}

QListWidget::item:selected {{
    background: {_C['overlay']};
    color: {_C['accent']};
}}

QListWidget::item:hover:!selected {{
    background: {_C['overlay']};
}}

QCheckBox {{
    spacing: 8px;
    color: {_C['text']};
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {_C['overlay']};
    border-radius: 3px;
    background: {_C['surface']};
}}

QCheckBox::indicator:checked {{
    background: {_C['accent']};
    border-color: {_C['accent']};
}}

QScrollArea {{
    border: none;
    background: {_C['bg']};
}}

QScrollBar:vertical {{
    background: {_C['bg']};
    width: 10px;
    border-radius: 5px;
}}

QScrollBar::handle:vertical {{
    background: {_C['overlay']};
    border-radius: 5px;
    min-height: 20px;
}}

QScrollBar::handle:vertical:hover {{
    background: {_C['subtext']};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
"""


class SettingsPanel(QWidget):
    """Panel for configuring application settings, model defaults, and managing recent projects."""

    settings_changed = Signal()
    open_recent_project = Signal(str)  # file path
    request_new_from_template = Signal(object)  # ProjectTemplate

    def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._updating = False
        self._build_ui()
        self._populate_from_settings()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_settings(self, settings: AppSettings) -> None:
        """Swap the current settings object and repopulate all fields."""
        self._settings = settings
        self._populate_from_settings()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.setStyleSheet(_DARK_STYLE)
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # Tab widget
        self._tabs = QTabWidget()
        root.addWidget(self._tabs, stretch=1)

        # Tab 1: Model & Generation
        tab1_container = QWidget()
        tab1_scroll = QScrollArea()
        tab1_scroll.setWidgetResizable(True)
        tab1_scroll.setWidget(tab1_container)
        tab1_inner = QVBoxLayout(tab1_container)
        tab1_inner.setContentsMargins(4, 4, 4, 4)
        tab1_inner.setSpacing(10)

        tab1_inner.addWidget(self._build_model_defaults_group())
        tab1_inner.addWidget(self._build_sampling_defaults_group())
        tab1_inner.addWidget(self._build_generation_defaults_group())
        tab1_inner.addWidget(self._build_export_group())
        tab1_inner.addStretch()

        self._tabs.addTab(tab1_scroll, "Model & Generation")

        # Tab 2: UI & Recent
        tab2_container = QWidget()
        tab2_scroll = QScrollArea()
        tab2_scroll.setWidgetResizable(True)
        tab2_scroll.setWidget(tab2_container)
        tab2_inner = QVBoxLayout(tab2_container)
        tab2_inner.setContentsMargins(4, 4, 4, 4)
        tab2_inner.setSpacing(10)

        tab2_inner.addWidget(self._build_editor_group())
        tab2_inner.addWidget(self._build_recent_projects_group())
        tab2_inner.addWidget(self._build_templates_group())
        tab2_inner.addStretch()

        self._tabs.addTab(tab2_scroll, "UI & Recent")

        # Save button at the bottom
        self._save_btn = QPushButton("Save Settings")
        self._save_btn.setFixedHeight(36)
        self._save_btn.clicked.connect(self._on_save)
        root.addWidget(self._save_btn)

    # -- Tab 1 sections -------------------------------------------------------

    def _build_model_defaults_group(self) -> QGroupBox:
        group = QGroupBox("Model Defaults")
        form = QFormLayout(group)
        form.setSpacing(10)

        # Default Model Path (with browse button)
        model_row = QHBoxLayout()
        self._model_path_edit = QLineEdit()
        self._model_path_edit.setPlaceholderText("Path to .gguf model file…")
        model_browse_btn = QPushButton("…")
        model_browse_btn.setFixedWidth(36)
        model_browse_btn.clicked.connect(self._on_browse_model_path)
        model_row.addWidget(self._model_path_edit, stretch=1)
        model_row.addWidget(model_browse_btn)
        form.addRow("Default Model Path:", model_row)

        # Default Context Size
        self._ctx_size_spin = QSpinBox()
        self._ctx_size_spin.setRange(1024, 131072)
        self._ctx_size_spin.setSingleStep(1024)
        self._ctx_size_spin.setValue(8192)
        self._ctx_size_spin.setSuffix(" tokens")
        form.addRow("Default Context Size:", self._ctx_size_spin)

        # Default GPU Layers
        self._gpu_layers_spin = QSpinBox()
        self._gpu_layers_spin.setRange(-1, 128)
        self._gpu_layers_spin.setValue(-1)
        self._gpu_layers_spin.setSpecialValueText("All")
        form.addRow("Default GPU Layers:", self._gpu_layers_spin)

        return group

    def _build_sampling_defaults_group(self) -> QGroupBox:
        group = QGroupBox("Sampling Defaults")
        form = QFormLayout(group)
        form.setSpacing(10)

        # Temperature
        self._temperature_spin = QDoubleSpinBox()
        self._temperature_spin.setRange(0.0, 2.0)
        self._temperature_spin.setSingleStep(0.05)
        self._temperature_spin.setDecimals(2)
        self._temperature_spin.setValue(0.75)
        form.addRow("Default Temperature:", self._temperature_spin)

        # Top P
        self._top_p_spin = QDoubleSpinBox()
        self._top_p_spin.setRange(0.0, 1.0)
        self._top_p_spin.setSingleStep(0.05)
        self._top_p_spin.setDecimals(2)
        self._top_p_spin.setValue(0.92)
        form.addRow("Default Top P:", self._top_p_spin)

        # Top K
        self._top_k_spin = QSpinBox()
        self._top_k_spin.setRange(0, 200)
        self._top_k_spin.setValue(50)
        form.addRow("Default Top K:", self._top_k_spin)

        # Repeat Penalty
        self._repeat_penalty_spin = QDoubleSpinBox()
        self._repeat_penalty_spin.setRange(0.5, 2.0)
        self._repeat_penalty_spin.setSingleStep(0.05)
        self._repeat_penalty_spin.setDecimals(2)
        self._repeat_penalty_spin.setValue(1.12)
        form.addRow("Default Repeat Penalty:", self._repeat_penalty_spin)

        return group

    def _build_generation_defaults_group(self) -> QGroupBox:
        group = QGroupBox("Generation Defaults")
        form = QFormLayout(group)
        form.setSpacing(10)

        # Words per Chapter
        self._words_per_chapter_spin = QSpinBox()
        self._words_per_chapter_spin.setRange(500, 20000)
        self._words_per_chapter_spin.setSingleStep(500)
        self._words_per_chapter_spin.setValue(2000)
        self._words_per_chapter_spin.setSuffix(" words")
        form.addRow("Default Words per Chapter:", self._words_per_chapter_spin)

        # Context Strategy
        self._context_strategy_combo = QComboBox()
        self._context_strategy_combo.addItems([
            "rolling_summary", "full_context", "sliding_window",
        ])
        form.addRow("Default Context Strategy:", self._context_strategy_combo)

        # Sliding Window Size
        self._sliding_window_spin = QSpinBox()
        self._sliding_window_spin.setRange(1, 10)
        self._sliding_window_spin.setValue(3)
        self._sliding_window_spin.setSuffix(" chapters")
        form.addRow("Sliding Window Size:", self._sliding_window_spin)

        return group

    def _build_export_group(self) -> QGroupBox:
        group = QGroupBox("Export")
        form = QFormLayout(group)
        form.setSpacing(10)

        # Default Export Directory (with browse button)
        export_row = QHBoxLayout()
        self._export_dir_edit = QLineEdit()
        self._export_dir_edit.setPlaceholderText("Default export directory…")
        export_browse_btn = QPushButton("…")
        export_browse_btn.setFixedWidth(36)
        export_browse_btn.clicked.connect(self._on_browse_export_dir)
        export_row.addWidget(self._export_dir_edit, stretch=1)
        export_row.addWidget(export_browse_btn)
        form.addRow("Default Export Directory:", export_row)

        return group

    # -- Tab 2 sections -------------------------------------------------------

    def _build_editor_group(self) -> QGroupBox:
        group = QGroupBox("Editor")
        form = QFormLayout(group)
        form.setSpacing(10)

        # Font Size
        self._font_size_spin = QSpinBox()
        self._font_size_spin.setRange(8, 24)
        self._font_size_spin.setValue(13)
        self._font_size_spin.setSuffix(" px")
        form.addRow("Font Size:", self._font_size_spin)

        # Editor Font Family
        self._font_family_edit = QLineEdit()
        self._font_family_edit.setText("Monospace")
        form.addRow("Editor Font Family:", self._font_family_edit)

        # Show Line Numbers
        self._line_numbers_check = QCheckBox("Show Line Numbers")
        self._line_numbers_check.setChecked(True)
        form.addRow(self._line_numbers_check)

        return group

    def _build_recent_projects_group(self) -> QGroupBox:
        group = QGroupBox("Recent Projects")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        self._recent_list = QListWidget()
        self._recent_list.setMaximumHeight(180)
        self._recent_list.currentRowChanged.connect(self._on_recent_project_clicked)
        layout.addWidget(self._recent_list)

        self._clear_recent_btn = QPushButton("Clear Recent Projects")
        self._clear_recent_btn.clicked.connect(self._on_clear_recent)
        layout.addWidget(self._clear_recent_btn)

        return group

    def _build_templates_group(self) -> QGroupBox:
        group = QGroupBox("Quick Start Templates")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        self._template_list = QListWidget()
        self._template_list.setMaximumHeight(220)
        for tpl in BUILT_IN_TEMPLATES:
            self._template_list.addItem(f"{tpl.name}  —  {tpl.description}")
        layout.addWidget(self._template_list)

        self._create_from_template_btn = QPushButton("Create from Template")
        self._create_from_template_btn.clicked.connect(self._on_create_from_template)
        layout.addWidget(self._create_from_template_btn)

        return group

    # ------------------------------------------------------------------
    # Populate / sync from settings
    # ------------------------------------------------------------------

    def _populate_from_settings(self) -> None:
        """Fill all widgets from the current AppSettings object."""
        self._updating = True
        try:
            s = self._settings

            # Model Defaults
            self._model_path_edit.setText(s.default_model_path)
            self._ctx_size_spin.setValue(s.default_ctx_size)
            self._gpu_layers_spin.setValue(s.default_gpu_layers)

            # Sampling Defaults
            self._temperature_spin.setValue(s.default_temperature)
            self._top_p_spin.setValue(s.default_top_p)
            self._top_k_spin.setValue(s.default_top_k)
            self._repeat_penalty_spin.setValue(s.default_repeat_penalty)

            # Generation Defaults
            self._words_per_chapter_spin.setValue(s.default_words_per_chapter)
            idx = self._context_strategy_combo.findText(s.default_context_strategy)
            self._context_strategy_combo.setCurrentIndex(max(idx, 0))
            self._sliding_window_spin.setValue(s.default_sliding_window_size)

            # Export
            self._export_dir_edit.setText(s.default_export_dir)

            # Editor
            self._font_size_spin.setValue(s.font_size)
            self._font_family_edit.setText(s.editor_font)
            self._line_numbers_check.setChecked(s.show_line_numbers)

            # Recent Projects
            self._refresh_recent_list()

            # Templates — static, already populated in _build_templates_group
        finally:
            self._updating = False

    def _refresh_recent_list(self) -> None:
        """Rebuild the recent-projects QListWidget from settings."""
        self._recent_list.blockSignals(True)
        self._recent_list.clear()
        for path in self._settings.recent_projects:
            self._recent_list.addItem(path)
        self._recent_list.blockSignals(False)

    # ------------------------------------------------------------------
    # Slot handlers — browse buttons
    # ------------------------------------------------------------------

    def _on_browse_model_path(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Model File", "",
            "GGUF Models (*.gguf);;All Files (*)",
        )
        if path:
            self._model_path_edit.setText(path)

    def _on_browse_export_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Select Export Directory",
            self._export_dir_edit.text() or "",
        )
        if path:
            self._export_dir_edit.setText(path)

    # ------------------------------------------------------------------
    # Slot handlers — recent projects
    # ------------------------------------------------------------------

    def _on_recent_project_clicked(self, row: int) -> None:
        if row < 0:
            return
        path = self._settings.recent_projects[row] if row < len(self._settings.recent_projects) else None
        if path:
            self.open_recent_project.emit(path)

    def _on_clear_recent(self) -> None:
        self._settings.recent_projects.clear()
        self._refresh_recent_list()

    # ------------------------------------------------------------------
    # Slot handlers — templates
    # ------------------------------------------------------------------

    def _on_create_from_template(self) -> None:
        row = self._template_list.currentRow()
        if 0 <= row < len(BUILT_IN_TEMPLATES):
            self.request_new_from_template.emit(BUILT_IN_TEMPLATES[row])

    # ------------------------------------------------------------------
    # Slot handlers — save
    # ------------------------------------------------------------------

    def _on_save(self) -> None:
        """Write widget values back to the AppSettings object and emit signal."""
        s = self._settings

        # Model Defaults
        s.default_model_path = self._model_path_edit.text()
        s.default_ctx_size = self._ctx_size_spin.value()
        s.default_gpu_layers = self._gpu_layers_spin.value()

        # Sampling Defaults
        s.default_temperature = self._temperature_spin.value()
        s.default_top_p = self._top_p_spin.value()
        s.default_top_k = self._top_k_spin.value()
        s.default_repeat_penalty = self._repeat_penalty_spin.value()

        # Generation Defaults
        s.default_words_per_chapter = self._words_per_chapter_spin.value()
        s.default_context_strategy = self._context_strategy_combo.currentText()
        s.default_sliding_window_size = self._sliding_window_spin.value()

        # Export
        s.default_export_dir = self._export_dir_edit.text()

        # Editor
        s.font_size = self._font_size_spin.value()
        s.editor_font = self._font_family_edit.text()
        s.show_line_numbers = self._line_numbers_check.isChecked()

        self.settings_changed.emit()