"""Chapter editor panel with live markdown preview, find & replace,
single-chapter regeneration/refinement, and revision history.
"""

from __future__ import annotations

import re
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QTextCursor, QKeySequence
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QComboBox,
    QLabel, QPushButton, QPlainTextEdit, QTextEdit, QFrame,
    QDialog, QLineEdit, QCheckBox, QListWidget, QListWidgetItem,
)

from ..models.book_project import BookProject

# ---------------------------------------------------------------------------
# Catppuccin Mocha palette
# ---------------------------------------------------------------------------
_BG = "#1e1e2e"
_SURFACE = "#313244"
_OVERLAY = "#45475a"
_TEXT = "#cdd6f4"
_SUBTEXT = "#a6adc8"
_ACCENT = "#89b4fa"
_GREEN = "#a6e3a1"
_RED = "#f38ba8"
_YELLOW = "#f9e2af"
_MANTLE = "#181825"

_PANEL_STYLE = f"""
QWidget#chapterEditorPanel {{ background-color: {_BG}; }}
QComboBox {{ background-color: {_SURFACE}; color: {_TEXT}; border: 1px solid {_OVERLAY}; padding: 5px 10px; border-radius: 4px; font-size: 12px; min-width: 220px; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{ image: none; border-left: 5px solid transparent; border-right: 5px solid transparent; border-top: 6px solid {_SUBTEXT}; margin-right: 8px; }}
QComboBox QAbstractItemView {{ background-color: {_SURFACE}; color: {_TEXT}; border: 1px solid {_OVERLAY}; selection-background-color: {_OVERLAY}; selection-color: {_ACCENT}; }}
QPlainTextEdit#markdownEditor {{ background-color: {_SURFACE}; color: {_TEXT}; border: 1px solid {_OVERLAY}; border-radius: 4px; padding: 10px; font-size: 13px; selection-background-color: {_OVERLAY}; }}
QTextEdit#previewPane {{ background-color: {_MANTLE}; color: {_TEXT}; border: 1px solid {_OVERLAY}; border-top: 2px solid {_ACCENT}; border-radius: 4px; padding: 10px; font-size: 14px; }}
"""


class FindReplaceDialog(QDialog):
    """Find & Replace dialog."""

    def __init__(self, editor: QPlainTextEdit, parent=None):
        super().__init__(parent)
        self._editor = editor
        self.setWindowTitle("Find & Replace")
        self.setMinimumWidth(450)
        self.setStyleSheet(f"QDialog {{ background-color: {_BG}; }} QLabel {{ color: {_TEXT}; }} QLineEdit {{ background-color: {_SURFACE}; color: {_TEXT}; border: 1px solid {_OVERLAY}; padding: 6px; border-radius: 4px; }} QPushButton {{ background-color: {_SURFACE}; color: {_TEXT}; border: 1px solid {_OVERLAY}; padding: 6px 14px; border-radius: 4px; }} QPushButton:hover {{ background-color: {_OVERLAY}; }} QCheckBox {{ color: {_TEXT}; }}")

        layout = QVBoxLayout(self)

        # Find row
        find_row = QHBoxLayout()
        find_row.addWidget(QLabel("Find:"))
        self._find_input = QLineEdit()
        self._find_input.setPlaceholderText("Search text...")
        find_row.addWidget(self._find_input)
        btn_find = QPushButton("Find Next")
        btn_find.clicked.connect(self._find_next)
        find_row.addWidget(btn_find)
        btn_find_prev = QPushButton("Find Prev")
        btn_find_prev.clicked.connect(self._find_prev)
        find_row.addWidget(btn_find_prev)
        layout.addLayout(find_row)

        # Replace row
        repl_row = QHBoxLayout()
        repl_row.addWidget(QLabel("Replace:"))
        self._replace_input = QLineEdit()
        self._replace_input.setPlaceholderText("Replacement text...")
        repl_row.addWidget(self._replace_input)
        btn_replace = QPushButton("Replace")
        btn_replace.clicked.connect(self._replace_one)
        repl_row.addWidget(btn_replace)
        btn_all = QPushButton("Replace All")
        btn_all.clicked.connect(self._replace_all)
        repl_row.addWidget(btn_all)
        layout.addLayout(repl_row)

        # Options
        self._case_cb = QCheckBox("Case sensitive")
        layout.addWidget(self._case_cb)
        self._regex_cb = QCheckBox("Regular expressions")
        layout.addWidget(self._regex_cb)

        self._find_input.returnPressed.connect(self._find_next)

    def _get_flags(self):
        flags = QTextCursor.FindFlag(0)
        if self._case_cb.isChecked():
            flags |= QTextCursor.FindFlag.FindCaseSensitively
        return flags

    def _find_next(self):
        text = self._find_input.text()
        if not text:
            return
        flags = self._get_flags()
        found = self._editor.find(text, flags)
        if not found:
            # Wrap around
            cursor = self._editor.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self._editor.setTextCursor(cursor)
            self._editor.find(text, flags)

    def _find_prev(self):
        text = self._find_input.text()
        if not text:
            return
        flags = self._get_flags() | QTextCursor.FindFlag.FindBackward
        self._editor.find(text, flags)

    def _replace_one(self):
        cursor = self._editor.textCursor()
        if cursor.hasSelection():
            selected = cursor.selectedText()
            find_text = self._find_input.text()
            if (self._case_cb.isChecked() and selected == find_text) or \
               (not self._case_cb.isChecked() and selected.lower() == find_text.lower()):
                cursor.insertText(self._replace_input.text())
        self._find_next()

    def _replace_all(self):
        text = self._editor.toPlainText()
        find_text = self._find_input.text()
        repl_text = self._replace_input.text()
        if not find_text:
            return
        if self._regex_cb.isChecked():
            flags = re.IGNORECASE if not self._case_cb.isChecked() else 0
            new_text, count = re.subn(find_text, repl_text, text, flags=flags)
        else:
            if self._case_cb.isChecked():
                new_text = text.replace(find_text, repl_text)
                count = text.count(find_text)
            else:
                new_text = re.sub(re.escape(find_text), repl_text, text, flags=re.IGNORECASE)
                count = len(re.findall(re.escape(find_text), text, re.IGNORECASE))
        self._editor.setPlainText(new_text)
        self._find_input.setFocus()


class RevisionHistoryDialog(QDialog):
    """Dialog showing revision history for a chapter."""

    def __init__(self, revisions, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Revision History")
        self.setMinimumSize(600, 500)
        self._revisions = revisions
        self.setStyleSheet(
            f"QDialog {{ background-color: {_BG}; }} "
            f"QLabel {{ color: {_TEXT}; }} "
            f"QListWidget {{ background-color: {_SURFACE}; color: {_TEXT}; border: 1px solid {_OVERLAY}; }} "
            f"QListWidget::item:selected {{ background-color: {_OVERLAY}; color: {_ACCENT}; }} "
            f"QTextEdit {{ background-color: {_SURFACE}; color: {_TEXT}; border: 1px solid {_OVERLAY}; font-family: monospace; font-size: 12px; }} "
            f"QPushButton {{ background-color: {_SURFACE}; color: {_TEXT}; border: 1px solid {_OVERLAY}; padding: 6px 14px; border-radius: 4px; }} "
            f"QPushButton:hover {{ background-color: {_OVERLAY}; }}"
        )
        self._selected_content = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Revisions (newest first):"))

        self._list = QListWidget()
        for r in reversed(revisions):
            self._list.addItem(f"[{r.timestamp}] {r.label} — {r.word_count:,} words")
        self._list.currentRowChanged.connect(self._on_selection)
        layout.addWidget(self._list)

        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        layout.addWidget(self._preview)

        btn_row = QHBoxLayout()
        btn_restore = QPushButton("Restore Selected Revision")
        btn_restore.clicked.connect(self._restore)
        btn_row.addWidget(btn_restore)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def _on_selection(self, row):
        if 0 <= row < len(self._revisions):
            rev = self._revisions[len(self._revisions) - 1 - row]
            self._preview.setPlainText(rev.content[:5000] + ("..." if len(rev.content) > 5000 else ""))
            self._selected_content = rev.content

    def _restore(self):
        if self._selected_content is not None:
            self._restored_content = self._selected_content
            self.accept()


class ChapterEditorPanel(QWidget):
    """Right-hand panel for viewing/editing chapter content."""

    # Signals for main window to handle
    request_regenerate = Signal(int)   # chapter index
    request_refine = Signal(int)       # chapter index
    request_save_revision = Signal(int)  # chapter index

    def __init__(self, project: BookProject) -> None:
        super().__init__()
        self.setObjectName("chapterEditorPanel")
        self._project: Optional[BookProject] = project
        self._current_index: int = -1
        self._preview_visible: bool = True
        self._build_ui()
        self.refresh_chapters()

    def set_project(self, project: BookProject) -> None:
        self._project = project
        self._current_index = -1
        self.refresh_chapters()

    def refresh_chapters(self) -> None:
        self._chapter_combo.blockSignals(True)
        self._chapter_combo.clear()
        if self._project is None:
            self._chapter_combo.blockSignals(False)
            self._update_status_bar()
            return
        for idx, ch in enumerate(self._project.chapters):
            status = " *" if ch.content_generated else ""
            self._chapter_combo.addItem(f"Ch {idx + 1}: {ch.title}{status}")
        if 0 <= self._current_index < self._chapter_combo.count():
            self._chapter_combo.setCurrentIndex(self._current_index)
        elif self._chapter_combo.count() > 0:
            self._chapter_combo.setCurrentIndex(0)
            self._current_index = 0
            self._load_chapter(0)
        self._chapter_combo.blockSignals(False)
        self._update_status_bar()

    def set_current_chapter(self, index: int) -> None:
        if self._project is None or not self._project.chapters:
            return
        if index < 0 or index >= len(self._project.chapters):
            return
        self._current_index = index
        self._chapter_combo.blockSignals(True)
        self._chapter_combo.setCurrentIndex(index)
        self._chapter_combo.blockSignals(False)
        self._load_chapter(index)

    def append_live_preview(self, token: str) -> None:
        if self._project is None or self._current_index < 0:
            return
        cursor = self._editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(token)
        self._editor.setTextCursor(cursor)
        self._editor.ensureCursorVisible()
        chapter = self._project.get_chapter(self._current_index)
        if chapter is not None:
            chapter.content_markdown += token
            html = self._markdown_to_html(chapter.content_markdown)
            self._preview.setHtml(html)
            scroll_bar = self._preview.verticalScrollBar()
            scroll_bar.setValue(scroll_bar.maximum())
        self._update_word_count()

    def toggle_preview(self) -> None:
        self._preview_visible = not self._preview_visible
        self._preview.setVisible(self._preview_visible)
        self._toggle_btn.setText("Hide Preview" if self._preview_visible else "Show Preview")

    def show_find_replace(self) -> None:
        dlg = FindReplaceDialog(self._editor, self)
        dlg.show()

    def _build_ui(self) -> None:
        self.setStyleSheet(_PANEL_STYLE)
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(5)

        # --- Top bar (row 1) ---
        row1 = QHBoxLayout()
        row1.setSpacing(6)
        self._chapter_combo = QComboBox()
        self._chapter_combo.currentIndexChanged.connect(self._on_chapter_selected)
        row1.addWidget(self._chapter_combo)

        self._word_count_label = QLabel("Words: 0")
        self._word_count_label.setStyleSheet(f"color: {_ACCENT}; font-weight: bold; padding: 0 12px;")
        row1.addWidget(self._word_count_label)
        row1.addStretch()

        for text, slot, color in [
            ("Save", self._save_chapter, _GREEN),
            ("Regenerate", self._on_regenerate, _RED),
            ("Refine", self._on_refine, _YELLOW),
        ]:
            btn = QPushButton(text)
            btn.setStyleSheet(f"background-color: {_SURFACE}; color: {color}; border: 1px solid {color}; padding: 5px 12px; border-radius: 4px; font-weight: bold; font-size: 12px;")
            btn.clicked.connect(slot)
            row1.addWidget(btn)

        self._toggle_btn = QPushButton("Hide Preview")
        self._toggle_btn.setStyleSheet(f"background-color: {_SURFACE}; color: {_ACCENT}; border: 1px solid {_ACCENT}; padding: 5px 12px; border-radius: 4px; font-weight: bold; font-size: 12px;")
        self._toggle_btn.clicked.connect(self.toggle_preview)
        row1.addWidget(self._toggle_btn)

        root.addLayout(row1)

        # --- Top bar (row 2) — revision & tools ---
        row2 = QHBoxLayout()
        row2.setSpacing(6)
        btn_history = QPushButton("Revision History")
        btn_history.setStyleSheet(f"background-color: {_SURFACE}; color: {_SUBTEXT}; border: 1px solid {_OVERLAY}; padding: 4px 10px; border-radius: 4px; font-size: 11px;")
        btn_history.clicked.connect(self._show_revision_history)
        row2.addWidget(btn_history)

        btn_save_rev = QPushButton("Save Revision")
        btn_save_rev.setStyleSheet(f"background-color: {_SURFACE}; color: {_SUBTEXT}; border: 1px solid {_OVERLAY}; padding: 4px 10px; border-radius: 4px; font-size: 11px;")
        btn_save_rev.clicked.connect(self._on_save_revision)
        row2.addWidget(btn_save_rev)

        row2.addStretch()
        row2.addWidget(QLabel(f"<span style='color:{_SUBTEXT}; font-size:11px;'>Ctrl+F: Find & Replace</span>"))
        root.addLayout(row2)

        # --- Splitter (editor / preview) ---
        self._vsplitter = QSplitter(Qt.Orientation.Vertical)
        self._editor = QPlainTextEdit()
        self._editor.setObjectName("markdownEditor")
        self._editor.setPlaceholderText("Select a chapter to begin editing...")
        monospace = QFont("Monospace", 13)
        monospace.setStyleHint(QFont.StyleHint.Monospace)
        self._editor.setFont(monospace)
        self._editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self._vsplitter.addWidget(self._editor)

        self._preview = QTextEdit()
        self._preview.setObjectName("previewPane")
        self._preview.setReadOnly(True)
        self._preview.setOpenExternalLinks(False)
        self._preview.setPlaceholderText("Rendered preview will appear here...")
        self._vsplitter.addWidget(self._preview)
        self._vsplitter.setStretchFactor(0, 3)
        self._vsplitter.setStretchFactor(1, 2)
        self._vsplitter.setSizes([500, 300])
        root.addWidget(self._vsplitter, stretch=1)

        # --- Bottom bar ---
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet(f"color: {_OVERLAY};")
        root.addWidget(separator)

        bottom_bar = QHBoxLayout()
        self._status_label = QLabel("Chapter 0 of 0 | Status: -")
        self._status_label.setStyleSheet(f"color: {_SUBTEXT}; font-size: 11px;")
        bottom_bar.addWidget(self._status_label)
        bottom_bar.addStretch()
        self._synopsis_label = QLabel("")
        self._synopsis_label.setStyleSheet(f"color: {_SUBTEXT}; font-size: 11px; font-style: italic;")
        self._synopsis_label.setWordWrap(True)
        self._synopsis_label.setMaximumWidth(500)
        bottom_bar.addWidget(self._synopsis_label)
        root.addLayout(bottom_bar)

    def _load_chapter(self, index: int) -> None:
        if self._project is None:
            return
        chapter = self._project.get_chapter(index)
        if chapter is None:
            self._editor.clear()
            self._preview.clear()
            self._update_status_bar()
            return
        self._current_index = index
        self._editor.setPlainText(chapter.content_markdown)
        html = self._markdown_to_html(chapter.content_markdown)
        self._preview.setHtml(html)
        self._update_word_count()
        self._update_status_bar()

    def _save_chapter(self) -> None:
        if self._project is None or self._current_index < 0:
            return
        chapter = self._project.get_chapter(self._current_index)
        if chapter is None:
            return
        text = self._editor.toPlainText()
        chapter.content_markdown = text
        chapter.word_count = len(text.split()) if text.strip() else 0
        chapter.content_generated = bool(text.strip())
        html = self._markdown_to_html(text)
        self._preview.setHtml(html)
        self._update_word_count()

    def _on_regenerate(self) -> None:
        if self._current_index >= 0:
            self.request_regenerate.emit(self._current_index)

    def _on_refine(self) -> None:
        if self._current_index >= 0:
            self.request_refine.emit(self._current_index)

    def _on_save_revision(self) -> None:
        if self._current_index >= 0:
            self.request_save_revision.emit(self._current_index)

    def _show_revision_history(self) -> None:
        if (self._project is None or self._current_index < 0
                or self._project.revision_history is None):
            return
        chapter = self._project.get_chapter(self._current_index)
        if not chapter:
            return
        revisions = self._project.revision_history.get_chapter_revisions(chapter.id)
        if not revisions:
            self._status_label.setText("No revisions for this chapter.")
            return
        dlg = RevisionHistoryDialog(revisions, self)
        if dlg.exec() and hasattr(dlg, '_restored_content'):
            self._editor.setPlainText(dlg._restored_content)
            self._status_label.setText("Revision restored.")

    def _on_chapter_selected(self, index: int) -> None:
        if index < 0:
            return
        self._load_chapter(index)

    def _update_word_count(self) -> None:
        text = self._editor.toPlainText()
        count = len(text.split()) if text.strip() else 0
        self._word_count_label.setText(f"Words: {count:,}")

    def _update_status_bar(self) -> None:
        if self._project is None or not self._project.chapters:
            self._status_label.setText("Chapter 0 of 0 | Status: -")
            self._synopsis_label.setText("")
            return
        total = len(self._project.chapters)
        idx = self._current_index + 1 if self._current_index >= 0 else 0
        chapter = self._project.get_chapter(self._current_index) if self._current_index >= 0 else None
        if chapter is not None:
            status = "Generated" if chapter.content_generated else "Not Generated"
            self._status_label.setText(f"Chapter {idx} of {total} | Status: {status}")
            synopsis = chapter.synopsis.strip()
            if len(synopsis) > 120:
                synopsis = synopsis[:117] + "..."
            self._synopsis_label.setText(synopsis or "")
        else:
            self._status_label.setText(f"Chapter {idx} of {total} | Status: -")
            self._synopsis_label.setText("")

    @staticmethod
    def _markdown_to_html(text: str) -> str:
        if not text:
            return ""
        lines = text.split("\n")
        html_parts: list[str] = []
        in_code_block = False
        code_buf: list[str] = []

        def _flush_code():
            if code_buf:
                code_html = "<br>".join(_escape_html(l) for l in code_buf)
                html_parts.append(
                    f'<pre style="background:{_SURFACE};color:{_GREEN};'
                    f'padding:12px;border-radius:6px;overflow-x:auto;'
                    f'font-family:monospace;font-size:13px;border:1px solid {_OVERLAY};">'
                    f"{code_html}</pre>"
                )
                code_buf.clear()

        i = 0
        while i < len(lines):
            line = lines[i]
            if line.strip().startswith("```"):
                if in_code_block:
                    _flush_code()
                    in_code_block = False
                else:
                    _flush_code()
                    in_code_block = True
                i += 1
                continue
            if in_code_block:
                code_buf.append(line)
                i += 1
                continue
            stripped = line.strip()
            if re.match(r"^-{3,}$", stripped) or re.match(r"^\*{3,}$", stripped):
                _flush_code()
                html_parts.append(f'<hr style="border:none;border-top:1px solid {_OVERLAY};margin:16px 0;">')
                i += 1
                continue
            hm = re.match(r"^(#{1,6})\s+(.*)", line)
            if hm:
                _flush_code()
                level = len(hm.group(1))
                content = _inline_format(hm.group(2))
                size = max(28 - (level - 1) * 4, 16)
                html_parts.append(f'<h{level} style="color:{_ACCENT};font-size:{size}px;margin:18px 0 8px 0;font-weight:bold;border-bottom:1px solid {_OVERLAY};padding-bottom:4px;">{content}</h{level}>')
                i += 1
                continue
            if stripped == "":
                _flush_code()
                if html_parts and html_parts[-1].startswith("<p"):
                    html_parts[-1] += "</p>"
                i += 1
                continue
            if html_parts and html_parts[-1].startswith("<p") and not html_parts[-1].endswith("</p>"):
                html_parts[-1] += "<br>" + _inline_format(stripped)
            elif html_parts and html_parts[-1].endswith("</p>"):
                html_parts.append(f"<p>{_inline_format(stripped)}")
            else:
                html_parts.append(f"<p>{_inline_format(stripped)}")
            i += 1
        _flush_code()
        if html_parts and html_parts[-1].startswith("<p") and not html_parts[-1].endswith("</p>"):
            html_parts[-1] += "</p>"
        body = "\n".join(html_parts)
        return f'<div style="font-family:sans-serif;color:{_TEXT};line-height:1.7;padding:4px;">{body}</div>'


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _inline_format(text: str) -> str:
    text = _escape_html(text)
    text = re.sub(r"`([^`]+)`", rf'<code style="background:{_SURFACE};color:{_GREEN};padding:2px 6px;border-radius:3px;font-family:monospace;font-size:12px;">\1</code>', text)
    text = re.sub(r"\*\*(.+?)\*\*", rf'<span style="font-weight:bold;color:{_TEXT};">\1</span>', text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", rf'<span style="font-style:italic;color:{_SUBTEXT};">\1</span>', text)
    return text