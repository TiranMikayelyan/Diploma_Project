"""Tabbed Verilog editor widget ready for integration into AI Verilog Studio."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QKeySequence, QAction, QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMessageBox,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .editor_pane import EditorPane, SUPPORTED_EXTENSIONS
from .find_replace import FindReplaceBar
from .theme import EditorTheme, DARK_THEME


class VerilogEditorWidget(QWidget):
    """
    Reusable multi-tab Verilog / SystemVerilog code editor.

    Public API
    ----------
    open_file(path)
    save_file()
    save_as(path)
    get_code()
    set_code(text)
    get_current_file()
    clear_editor()
    """

    file_opened = pyqtSignal(str)
    file_saved = pyqtSignal(str)
    current_file_changed = pyqtSignal(object)  # str | None

    def __init__(self, parent=None, theme: EditorTheme | None = None) -> None:
        super().__init__(parent)
        self._theme = theme or DARK_THEME
        self.setAcceptDrops(True)
        self._build_ui()
        self._apply_chrome_theme()
        self._create_actions()
        self._new_tab()

    # ================================================================== public

    def open_file(self, path: str) -> bool:
        """Open a ``.v`` / ``.sv`` file in a new or existing tab."""
        path_obj = Path(path)
        if not path_obj.is_file():
            QMessageBox.warning(self, "Open File", f"File not found:\n{path}")
            return False

        suffix = path_obj.suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            QMessageBox.warning(
                self,
                "Open File",
                "Only Verilog (.v) and SystemVerilog (.sv) files are supported.",
            )
            return False

        resolved = str(path_obj.resolve())
        existing = self._find_tab_by_path(resolved)
        if existing is not None:
            self._tabs.setCurrentWidget(existing)
            return True

        pane = self._current_pane()
        # Reuse a single empty untitled tab if present.
        if (
            pane is not None
            and pane.file_path is None
            and not pane.is_modified()
            and pane.text() == ""
            and self._tabs.count() == 1
        ):
            target = pane
        else:
            target = self._new_tab()

        try:
            target.load_from_path(resolved)
        except OSError as exc:
            QMessageBox.critical(self, "Open File", f"Could not open file:\n{exc}")
            return False

        self._update_tab_title(target)
        self._tabs.setCurrentWidget(target)
        self._update_status()
        self.file_opened.emit(resolved)
        self.current_file_changed.emit(resolved)
        return True

    def save_file(self) -> bool:
        """Save the current tab. Prompts for a path if unsaved."""
        pane = self._current_pane()
        if pane is None:
            return False
        if pane.file_path is None:
            return self.save_as()
        try:
            pane.save_to_path()
        except OSError as exc:
            QMessageBox.critical(self, "Save File", f"Could not save file:\n{exc}")
            return False
        self._update_tab_title(pane)
        self.file_saved.emit(pane.file_path)
        return True

    def save_as(self, path: str | None = None) -> bool:
        """Save the current tab to ``path``, or ask the user if omitted."""
        pane = self._current_pane()
        if pane is None:
            return False

        if path is None:
            start = pane.file_path or str(Path.home())
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Save As",
                start,
                "Verilog (*.v);;SystemVerilog (*.sv);;All Files (*)",
            )
            if not path:
                return False

        suffix = Path(path).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            # Default to .v when the user omits an extension.
            if suffix == "":
                path = path + ".v"
            else:
                QMessageBox.warning(
                    self,
                    "Save As",
                    "Only .v and .sv extensions are allowed.",
                )
                return False

        try:
            pane.save_to_path(path)
        except OSError as exc:
            QMessageBox.critical(self, "Save As", f"Could not save file:\n{exc}")
            return False

        self._update_tab_title(pane)
        self.file_saved.emit(pane.file_path or path)
        self.current_file_changed.emit(pane.file_path)
        return True

    def get_code(self) -> str:
        """Return the text of the active editor tab."""
        pane = self._current_pane()
        return pane.get_code() if pane else ""

    def set_code(self, text: str) -> None:
        """Replace the text of the active editor tab."""
        pane = self._current_pane()
        if pane is None:
            pane = self._new_tab()
        pane.set_code(text)

    def get_current_file(self) -> str | None:
        """Return the absolute path of the active file, or ``None``."""
        pane = self._current_pane()
        return pane.file_path if pane else None

    def clear_editor(self) -> None:
        """Clear the active tab and detach any associated file path."""
        pane = self._current_pane()
        if pane is None:
            return
        pane.clear_editor()
        self._update_tab_title(pane)
        self._update_status()
        self.current_file_changed.emit(None)

    def new_file(self) -> None:
        """Open a new empty untitled tab."""
        self._new_tab()

    # ================================================================== UI

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._find_bar = FindReplaceBar(self, self._theme)
        self._find_bar.find_next.connect(self._on_find_next)
        self._find_bar.find_previous.connect(self._on_find_previous)
        self._find_bar.replace_one.connect(self._on_replace_one)
        self._find_bar.replace_all.connect(self._on_replace_all)
        self._find_bar.closed.connect(self._on_find_closed)
        layout.addWidget(self._find_bar)

        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.setMovable(True)
        self._tabs.setDocumentMode(True)
        self._tabs.tabCloseRequested.connect(self._close_tab)
        self._tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self._tabs, stretch=1)

        self._status = QStatusBar()
        self._status.setSizeGripEnabled(False)
        self._position_label = QLabel("Ln 1, Col 1")
        self._file_label = QLabel("Untitled")
        self._status.addWidget(self._file_label, stretch=1)
        self._status.addPermanentWidget(self._position_label)
        layout.addWidget(self._status)

    def _apply_chrome_theme(self) -> None:
        t = self._theme
        self.setStyleSheet(
            f"""
            QWidget {{
                background-color: {t.background};
                color: {t.foreground};
            }}
            QTabWidget::pane {{
                border: none;
                background: {t.background};
            }}
            QTabBar::tab {{
                background: {t.tab_bg};
                color: {t.tab_fg};
                padding: 6px 14px;
                margin-right: 1px;
                border: none;
            }}
            QTabBar::tab:selected {{
                background: {t.tab_selected};
                border-top: 2px solid {t.status_bg};
            }}
            QTabBar::tab:hover {{
                background: #2a2d2e;
            }}
            QStatusBar {{
                background-color: {t.status_bg};
                color: {t.status_fg};
            }}
            QStatusBar QLabel {{
                color: {t.status_fg};
                padding: 0 8px;
            }}
            QMessageBox, QInputDialog, QFileDialog {{
                background-color: {t.tab_bg};
                color: {t.foreground};
            }}
            """
        )

    def _create_actions(self) -> None:
        # Shortcuts live on the widget so they work regardless of focus.
        bindings = [
            ("Ctrl+F", self._show_find),
            ("Ctrl+H", self._show_replace),
            ("Ctrl+G", self._go_to_line),
            ("Ctrl+S", self.save_file),
            ("Ctrl+Shift+S", lambda: self.save_as()),
            ("Ctrl+O", self._prompt_open),
            ("Ctrl+N", self._new_tab),
            ("Ctrl+W", self._close_current_tab),
            ("Ctrl+Z", self._undo),
            ("Ctrl+Y", self._redo),
            ("Ctrl+Shift+Z", self._redo),
        ]
        for seq, slot in bindings:
            action = QAction(self)
            action.setShortcut(QKeySequence(seq))
            action.triggered.connect(slot)
            self.addAction(action)

    # ================================================================== tabs

    def _new_tab(self) -> EditorPane:
        pane = EditorPane(self, self._theme)
        pane.cursor_position_changed.connect(self._on_cursor_position)
        pane.modification_changed.connect(
            lambda _m, p=pane: self._update_tab_title(p)
        )
        pane.file_dropped.connect(self.open_file)
        index = self._tabs.addTab(pane, pane.display_name())
        self._tabs.setCurrentIndex(index)
        pane.setFocus()
        return pane

    def _current_pane(self) -> EditorPane | None:
        widget = self._tabs.currentWidget()
        return widget if isinstance(widget, EditorPane) else None

    def _find_tab_by_path(self, path: str) -> EditorPane | None:
        resolved = str(Path(path).resolve())
        for i in range(self._tabs.count()):
            pane = self._tabs.widget(i)
            if isinstance(pane, EditorPane) and pane.file_path == resolved:
                return pane
        return None

    def _update_tab_title(self, pane: EditorPane) -> None:
        index = self._tabs.indexOf(pane)
        if index < 0:
            return
        title = pane.display_name()
        if pane.is_modified():
            title = f"*{title}"
        self._tabs.setTabText(index, title)
        self._tabs.setTabToolTip(index, pane.file_path or "Untitled")
        if pane is self._current_pane():
            self._file_label.setText(pane.file_path or "Untitled")

    def _close_tab(self, index: int) -> None:
        pane = self._tabs.widget(index)
        if not isinstance(pane, EditorPane):
            return
        if not self._confirm_close(pane):
            return
        self._tabs.removeTab(index)
        pane.deleteLater()
        if self._tabs.count() == 0:
            self._new_tab()

    def _close_current_tab(self) -> None:
        self._close_tab(self._tabs.currentIndex())

    def _confirm_close(self, pane: EditorPane) -> bool:
        if not pane.is_modified():
            return True
        name = pane.display_name()
        reply = QMessageBox.question(
            self,
            "Unsaved Changes",
            f"'{name}' has unsaved changes.\nDo you want to save before closing?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if reply == QMessageBox.StandardButton.Cancel:
            return False
        if reply == QMessageBox.StandardButton.Save:
            self._tabs.setCurrentWidget(pane)
            return self.save_file()
        return True

    def _on_tab_changed(self, _index: int) -> None:
        pane = self._current_pane()
        self._update_status()
        if pane:
            self._update_tab_title(pane)
            self.current_file_changed.emit(pane.file_path)
            pane.setFocus()

    # ================================================================== status

    def _on_cursor_position(self, line: int, column: int) -> None:
        self._position_label.setText(f"Ln {line}, Col {column}")

    def _update_status(self) -> None:
        pane = self._current_pane()
        if pane is None:
            self._position_label.setText("Ln 1, Col 1")
            self._file_label.setText("")
            return
        line, col = pane.getCursorPosition()
        self._position_label.setText(f"Ln {line + 1}, Col {col + 1}")
        self._file_label.setText(pane.file_path or "Untitled")

    # ================================================================== find

    def _show_find(self) -> None:
        pane = self._current_pane()
        selected = pane.selectedText() if pane else ""
        self._find_bar.show_find(selected)

    def _show_replace(self) -> None:
        pane = self._current_pane()
        selected = pane.selectedText() if pane else ""
        self._find_bar.show_replace(selected)

    def _on_find_closed(self) -> None:
        pane = self._current_pane()
        if pane:
            pane.setFocus()

    def _on_find_next(self, text: str, case: bool, whole: bool) -> None:
        pane = self._current_pane()
        if pane:
            pane.find_text(text, case_sensitive=case, whole_word=whole, forward=True)

    def _on_find_previous(self, text: str, case: bool, whole: bool) -> None:
        pane = self._current_pane()
        if pane:
            pane.find_text(text, case_sensitive=case, whole_word=whole, forward=False)

    def _on_replace_one(self, find: str, replace: str, case: bool, whole: bool) -> None:
        pane = self._current_pane()
        if pane:
            pane.replace_current(find, replace, case, whole)

    def _on_replace_all(self, find: str, replace: str, case: bool, whole: bool) -> None:
        pane = self._current_pane()
        if pane:
            pane.replace_all(find, replace, case, whole)

    def _go_to_line(self) -> None:
        pane = self._current_pane()
        if pane:
            pane.go_to_line()

    # ================================================================== edit

    def _undo(self) -> None:
        pane = self._current_pane()
        if pane:
            pane.undo()

    def _redo(self) -> None:
        pane = self._current_pane()
        if pane:
            pane.redo()

    def _prompt_open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Verilog File",
            str(Path.home()),
            "Verilog / SystemVerilog (*.v *.sv);;All Files (*)",
        )
        if path:
            self.open_file(path)

    # ================================================================== DnD

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if Path(url.toLocalFile()).suffix.lower() in SUPPORTED_EXTENSIONS:
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if Path(path).suffix.lower() in SUPPORTED_EXTENSIONS:
                self.open_file(path)
        event.acceptProposedAction()

    def closeEvent(self, event) -> None:  # noqa: N802
        """Prompt for unsaved tabs when the host window is closing."""
        for i in range(self._tabs.count()):
            pane = self._tabs.widget(i)
            if isinstance(pane, EditorPane) and pane.is_modified():
                self._tabs.setCurrentIndex(i)
                if not self._confirm_close(pane):
                    event.ignore()
                    return
        event.accept()