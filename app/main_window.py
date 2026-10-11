"""Main application window with multi-panel navigation."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction, QFont, QIcon
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QToolBar, QStatusBar, QTabWidget, QLabel, QFileDialog,
    QMessageBox, QComboBox, QPushButton, QFrame, QMenu,
)

from ..models.book_project import (
    BookProject, EbookType, GenerationState, EBOOK_TYPE_LABELS,
)
from ..ai.llm_backend import LLMBackend
from ..ai.prompt_engineer import PromptEngineer
from ..ai.context_engineer import ContextEngineer
from ..ai.harness import AIHarness, GenerationWorker
from .book_config import BookConfigPanel
from .chapter_editor import ChapterEditorPanel
from .prompt_templates import PromptTemplatePanel
from .generation import GenerationPanel

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application window with tab-based multi-panel layout."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Ebook Generator — AI-Powered Book Creation")
        self.setMinimumSize(1200, 800)
        self.resize(1400, 900)

        # --- AI Subsystem ---
        self._llm = LLMBackend()
        self._prompt_eng = PromptEngineer()
        self._context_eng = ContextEngineer()
        self._harness = AIHarness(self._llm, self._prompt_eng, self._context_eng)
        self._worker: Optional[GenerationWorker] = None

        # --- Project ---
        self._project = BookProject()

        # --- Build UI ---
        self._build_menu_bar()
        self._build_toolbar()
        self._build_central_widget()
        self._build_status_bar()

        # --- Connect signals ---
        self._connect_signals()

        # --- Apply style ---
        self._apply_style()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_menu_bar(self) -> None:
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        new_action = QAction("&New Project", self)
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self._new_project)
        file_menu.addAction(new_action)

        open_action = QAction("&Open Project...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._open_project)
        file_menu.addAction(open_action)

        save_action = QAction("&Save Project", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self._save_project)
        file_menu.addAction(save_action)

        save_as_action = QAction("Save &As...", self)
        save_as_action.setShortcut("Ctrl+Shift+S")
        save_as_action.triggered.connect(self._save_project_as)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        import_model_action = QAction("Load &GGUF Model...", self)
        import_model_action.triggered.connect(self._load_model_dialog)
        file_menu.addAction(import_model_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Export menu
        export_menu = menubar.addMenu("&Export")

        export_md_action = QAction("Export as &Markdown...", self)
        export_md_action.triggered.connect(self._export_markdown)
        export_menu.addAction(export_md_action)

        export_epub_action = QAction("Export as &EPUB...", self)
        export_epub_action.triggered.connect(self._export_epub)
        export_menu.addAction(export_epub_action)

        export_both_action = QAction("Export &Both (MD + EPUB)...", self)
        export_both_action.triggered.connect(self._export_both)
        export_menu.addAction(export_both_action)

        # View menu
        view_menu = menubar.addMenu("&View")
        self._toggle_preview_action = QAction("Toggle Live &Preview", self)
        self._toggle_preview_action.setShortcut("Ctrl+P")
        self._toggle_preview_action.triggered.connect(self._toggle_preview)
        view_menu.addAction(self._toggle_preview_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")
        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(toolbar)

        # New / Open / Save buttons
        btn_new = QPushButton(" New")
        btn_new.clicked.connect(self._new_project)
        toolbar.addWidget(btn_new)

        btn_open = QPushButton(" Open")
        btn_open.clicked.connect(self._open_project)
        toolbar.addWidget(btn_open)

        btn_save = QPushButton(" Save")
        btn_save.clicked.connect(self._save_project)
        toolbar.addWidget(btn_save)

        toolbar.addSeparator()

        # Model status
        self._model_label = QLabel("  No model loaded")
        self._model_label.setStyleSheet("color: #e74c3c; font-weight: bold; padding: 0 12px;")
        toolbar.addWidget(self._model_label)

        btn_load_model = QPushButton(" Load Model")
        btn_load_model.clicked.connect(self._load_model_dialog)
        toolbar.addWidget(btn_load_model)

        toolbar.addSeparator()

        # Context strategy
        toolbar.addWidget(QLabel("  Context: "))
        self._context_combo = QComboBox()
        self._context_combo.addItems(["rolling_summary", "full_context", "sliding_window"])
        self._context_combo.setCurrentText("rolling_summary")
        self._context_combo.setMinimumWidth(150)
        self._context_combo.currentTextChanged.connect(self._on_context_strategy_changed)
        toolbar.addWidget(self._context_combo)

    def _build_central_widget(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(6, 6, 6, 6)

        # Left sidebar: tab navigation
        self._sidebar_tabs = QTabWidget()
        self._sidebar_tabs.setTabPosition(QTabWidget.TabPosition.West)
        self._sidebar_tabs.setDocumentMode(True)
        self._sidebar_tabs.setMinimumWidth(380)
        self._sidebar_tabs.setMaximumWidth(480)

        # Panels
        self._config_panel = BookConfigPanel(self._project)
        self._template_panel = PromptTemplatePanel(self._project)
        self._generation_panel = GenerationPanel(self._project, self._harness)

        self._sidebar_tabs.addTab(self._config_panel, "Book Config")
        self._sidebar_tabs.addTab(self._template_panel, "Templates")
        self._sidebar_tabs.addTab(self._generation_panel, "Generate")

        # Right side: chapter editor with preview
        self._chapter_panel = ChapterEditorPanel(self._project)

        # Splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._sidebar_tabs)
        splitter.addWidget(self._chapter_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 5)

        layout.addWidget(splitter)

    def _build_status_bar(self) -> None:
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

        self._status_state = QLabel("Ready")
        self._status_state.setStyleSheet("font-weight: bold;")
        self._status_bar.addPermanentWidget(self._status_state)

        self._status_progress = QLabel("Progress: 0%")
        self._status_bar.addPermanentWidget(self._status_progress)

        self._status_words = QLabel("Words: 0")
        self._status_bar.addPermanentWidget(self._status_words)

        self._status_bar.showMessage("Welcome to Ebook Generator. Load a GGUF model to begin.")

    # ------------------------------------------------------------------
    # Signal connections
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        # Config panel → project sync
        self._config_panel.project_updated.connect(self._on_project_updated)

        # Config panel → chapter panel sync
        self._config_panel.chapters_changed.connect(self._chapter_panel.refresh_chapters)

        # Harness signals → UI updates
        self._harness.state_changed.connect(self._on_state_changed)
        self._harness.progress_changed.connect(self._on_progress_changed)
        self._harness.chapter_started.connect(self._on_chapter_started)
        self._harness.chapter_completed.connect(self._on_chapter_completed)
        self._harness.chapter_progress.connect(self._on_chapter_progress)
        self._harness.outline_generated.connect(self._on_outline_generated)
        self._harness.frontmatter_generated.connect(self._on_frontmatter_generated)
        self._harness.backmatter_generated.connect(self._on_backmatter_generated)
        self._harness.error_occurred.connect(self._on_error)
        self._harness.generation_finished.connect(self._on_generation_finished)
        self._harness.log_message.connect(self._on_log_message)

    # ------------------------------------------------------------------
    # Slot handlers
    # ------------------------------------------------------------------

    def _on_project_updated(self) -> None:
        """Called when book config changes."""
        self._harness.set_project(self._project)
        self._template_panel.refresh()
        self._generation_panel.refresh()
        self._update_word_count()

    def _on_context_strategy_changed(self, strategy: str) -> None:
        self._context_eng.strategy = strategy
        self._status_bar.showMessage(f"Context strategy: {strategy}", 3000)

    def _on_state_changed(self, state: str) -> None:
        self._status_state.setText(f"State: {state}")
        colors = {
            "idle": "#95a5a6", "planning": "#3498db",
            "generating_outline": "#9b59b6", "generating_chapter": "#2ecc71",
            "generating_frontmatter": "#9b59b6", "generating_backmatter": "#9b59b6",
            "paused": "#f39c12", "cancelled": "#e74c3c",
            "completed": "#27ae60", "error": "#e74c3c",
        }
        color = colors.get(state, "#333")
        self._status_state.setStyleSheet(f"font-weight: bold; color: {color};")

    def _on_progress_changed(self, pct: float) -> None:
        self._status_progress.setText(f"Progress: {pct:.1f}%")

    def _on_chapter_started(self, idx: int, title: str) -> None:
        self._chapter_panel.set_current_chapter(idx)
        self._generation_panel.log(f"\n{'='*50}\nStarting Chapter {idx+1}: {title}\n{'='*50}")

    def _on_chapter_completed(self, idx: int) -> None:
        self._chapter_panel.refresh_chapters()
        self._update_word_count()

    def _on_chapter_progress(self, token: str) -> None:
        self._chapter_panel.append_live_preview(token)
        self._generation_panel.append_output(token)

    def _on_outline_generated(self, outline: str) -> None:
        self._config_panel.set_outline(outline)

    def _on_frontmatter_generated(self, frontmatter: str) -> None:
        self._project.frontmatter = frontmatter

    def _on_backmatter_generated(self, backmatter: str) -> None:
        self._project.backmatter = backmatter

    def _on_error(self, msg: str) -> None:
        QMessageBox.critical(self, "Generation Error", msg)

    def _on_generation_finished(self) -> None:
        self._status_bar.showMessage("Generation complete!", 5000)
        self._chapter_panel.refresh_chapters()

    def _on_log_message(self, msg: str) -> None:
        self._generation_panel.log(msg)
        self._status_bar.showMessage(msg, 3000)

    def _update_word_count(self) -> None:
        total = self._project.total_words()
        gen = self._project.generated_count()
        self._status_words.setText(
            f"Words: {total:,} ({gen}/{len(self._project.chapters)} chapters)"
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _new_project(self) -> None:
        if self._project.state == GenerationState.GENERATING_CHAPTER:
            QMessageBox.warning(self, "Warning", "Stop generation before creating a new project.")
            return
        self._project = BookProject()
        self._config_panel.set_project(self._project)
        self._chapter_panel.set_project(self._project)
        self._template_panel.set_project(self._project)
        self._generation_panel.set_project(self._project)
        self._harness.set_project(self._project)
        self._update_word_count()
        self._status_bar.showMessage("New project created.", 3000)

    def _open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Project", "", "Ebook Project (*.eproj *.json)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._project = BookProject.from_dict(data)
            self._project.file_path = path
            self._config_panel.set_project(self._project)
            self._chapter_panel.set_project(self._project)
            self._template_panel.set_project(self._project)
            self._generation_panel.set_project(self._project)
            self._harness.set_project(self._project)
            self._update_word_count()
            self._status_bar.showMessage(f"Project loaded: {path}", 3000)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open project:\n{e}")

    def _save_project(self) -> None:
        if not self._project.file_path:
            self._save_project_as()
            return
        self._do_save(self._project.file_path)

    def _save_project_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Project As", "my_book.eproj", "Ebook Project (*.eproj)"
        )
        if path:
            if not path.endswith(".eproj"):
                path += ".eproj"
            self._project.file_path = path
            self._do_save(path)

    def _do_save(self, path: str) -> None:
        try:
            data = self._project.to_dict()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self._status_bar.showMessage(f"Project saved: {path}", 3000)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save project:\n{e}")

    def _load_model_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select GGUF Model", "", "GGUF Model (*.gguf *.bin)"
        )
        if not path:
            return
        try:
            self._status_bar.showMessage(f"Loading model: {Path(path).name}...")
            self._llm.load_model(path, n_ctx=8192, n_gpu_layers=-1)
            self._model_label.setText(f"  Model: {Path(path).name}")
            self._model_label.setStyleSheet("color: #27ae60; font-weight: bold; padding: 0 12px;")
            self._context_eng = ContextEngineer(
                count_tokens_fn=self._llm.count_tokens,
                strategy=self._context_combo.currentText(),
            )
            self._harness._context_eng = self._context_eng
            self._status_bar.showMessage(f"Model loaded: {Path(path).name}", 5000)
        except Exception as e:
            self._model_label.setText("  Load failed")
            self._model_label.setStyleSheet("color: #e74c3c; font-weight: bold; padding: 0 12px;")
            QMessageBox.critical(self, "Model Error", f"Failed to load model:\n{e}")

    def _export_markdown(self) -> None:
        from ..exporters.markdown_exporter import MarkdownExporter
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Markdown", f"{self._project.metadata.title}.md",
            "Markdown (*.md)"
        )
        if path:
            MarkdownExporter.export(self._project, path)
            self._status_bar.showMessage(f"Markdown exported: {path}", 5000)

    def _export_epub(self) -> None:
        from ..exporters.epub_exporter import EpubExporter
        path, _ = QFileDialog.getSaveFileName(
            self, "Export EPUB", f"{self._project.metadata.title}.epub",
            "EPUB (*.epub)"
        )
        if path:
            EpubExporter.export(self._project, path)
            self._status_bar.showMessage(f"EPUB exported: {path}", 5000)

    def _export_both(self) -> None:
        from ..exporters.markdown_exporter import MarkdownExporter
        from ..exporters.epub_exporter import EpubExporter
        dir_path = QFileDialog.getExistingDirectory(self, "Select Export Directory")
        if dir_path:
            base = self._project.metadata.title
            md_path = str(Path(dir_path) / f"{base}.md")
            epub_path = str(Path(dir_path) / f"{base}.epub")
            MarkdownExporter.export(self._project, md_path)
            EpubExporter.export(self._project, epub_path)
            self._status_bar.showMessage(
                f"Exported both to: {dir_path}", 5000
            )

    def _toggle_preview(self) -> None:
        self._chapter_panel.toggle_preview()

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About Ebook Generator",
            "<h3>Ebook Generator</h3>"
            "<p>AI-powered ebook creation with llama.cpp</p>"
            "<p>Features:</p>"
            "<ul>"
            "<li>15 ebook types with specialized prompts</li>"
            "<li>Context engineering (rolling summary, full, sliding window)</li>"
            "<li>AI Harness for pipeline orchestration</li>"
            "<li>Live generation preview</li>"
            "<li>Export to Markdown and EPUB</li>"
            "</ul>"
            "<p>Built with PySide6 + llama-cpp-python</p>",
        )

    # ------------------------------------------------------------------
    # Styling
    # ------------------------------------------------------------------

    def _apply_style(self) -> None:
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e2e;
            }
            QMenuBar {
                background-color: #181825;
                color: #cdd6f4;
                border-bottom: 1px solid #313244;
                padding: 2px;
            }
            QMenuBar::item:selected {
                background-color: #313244;
            }
            QMenu {
                background-color: #1e1e2e;
                color: #cdd6f4;
                border: 1px solid #313244;
            }
            QMenu::item:selected {
                background-color: #45475a;
            }
            QToolBar {
                background-color: #181825;
                border-bottom: 1px solid #313244;
                spacing: 6px;
                padding: 4px;
            }
            QStatusBar {
                background-color: #181825;
                color: #a6adc8;
                border-top: 1px solid #313244;
            }
            QTabWidget::pane {
                border: 1px solid #313244;
                background-color: #1e1e2e;
            }
            QTabBar::tab {
                background-color: #181825;
                color: #a6adc8;
                padding: 8px 16px;
                margin-right: 2px;
                border: 1px solid #313244;
                border-bottom: none;
            }
            QTabBar::tab:selected {
                background-color: #1e1e2e;
                color: #89b4fa;
                border-bottom: 2px solid #89b4fa;
            }
            QPushButton {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                padding: 6px 14px;
                border-radius: 4px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #45475a;
                border-color: #89b4fa;
            }
            QPushButton:pressed {
                background-color: #585b70;
            }
            QLineEdit, QTextEdit, QPlainTextEdit, QComboBox {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                padding: 6px;
                border-radius: 4px;
                font-size: 13px;
            }
            QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
                border-color: #89b4fa;
            }
            QLabel {
                color: #cdd6f4;
                font-size: 13px;
            }
            QGroupBox {
                color: #89b4fa;
                border: 1px solid #313244;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 14px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 6px;
            }
            QSpinBox, QDoubleSpinBox {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                padding: 4px;
                border-radius: 4px;
            }
            QListWidget, QListWidgetItem {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
            }
            QListWidget::item:selected {
                background-color: #45475a;
                color: #89b4fa;
            }
            QSplitter::handle {
                background-color: #313244;
                width: 2px;
            }
            QProgressBar {
                background-color: #313244;
                border: 1px solid #45475a;
                border-radius: 4px;
                text-align: center;
                color: #cdd6f4;
            }
            QProgressBar::chunk {
                background-color: #89b4fa;
                border-radius: 3px;
            }
            QScrollBar:vertical {
                background-color: #1e1e2e;
                width: 10px;
                border: none;
            }
            QScrollBar::handle:vertical {
                background-color: #45475a;
                border-radius: 5px;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
        """)

    def closeEvent(self, event) -> None:
        if self._project.state in (GenerationState.GENERATING_CHAPTER,
                                     GenerationState.GENERATING_OUTLINE):
            reply = QMessageBox.question(
                self, "Confirm Exit",
                "Generation is in progress. Are you sure you want to exit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
            self._harness.cancel()
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(3000)
        self._llm.unload_model()
        event.accept()