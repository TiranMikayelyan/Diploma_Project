"""Main window: existing Verilog editor plus parse / JSON / log panels.

Expects ``verilog_editor.editor_widget.VerilogEditorWidget`` to provide
``get_code()``, ``get_current_file()``, ``new_file()``, ``save_file()``,
``save_as()``, ``open_file(path)`` and ``closeEvent(event)``, and
``verilog_editor.theme.DARK_THEME`` to provide the colour fields used below.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QFont, QKeySequence
from PyQt6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from models.design_model import ParseResult
from services.parsing_service import ParsingService
from verilog_editor.editor_widget import VerilogEditorWidget
from verilog_editor.theme import DARK_THEME


class StudioWindow(QMainWindow):
    """Single application window. Reuses ``VerilogEditorWidget`` as-is."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("AI Verilog Studio")
        self.resize(1400, 860)
        self._theme = DARK_THEME
        self._parsing = ParsingService()
        self._last_result: ParseResult | None = None
        self._build_ui()
        self._build_menus()
        self._apply_theme()

    @property
    def editor(self) -> VerilogEditorWidget:
        return self._editor

    # ------------------------------------------------------------------- UI

    def _build_ui(self) -> None:
        t = self._theme
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        toolbar = QToolBar("Parse")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self._parse_button = QPushButton("Parse Verilog")
        self._parse_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._parse_button.clicked.connect(self.parse_verilog)
        toolbar.addWidget(self._parse_button)

        self._save_json_button = QPushButton("Save JSON")
        self._save_json_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_json_button.clicked.connect(self.save_json)
        toolbar.addWidget(self._save_json_button)

        vertical = QSplitter(Qt.Orientation.Vertical)
        horizontal = QSplitter(Qt.Orientation.Horizontal)

        self._editor = VerilogEditorWidget()
        editor_wrap = QWidget()
        editor_layout = QVBoxLayout(editor_wrap)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)
        editor_layout.addWidget(self._section_label("Verilog Editor"))
        editor_layout.addWidget(self._editor, stretch=1)
        horizontal.addWidget(editor_wrap)

        font = QFont("Consolas", 10)
        if not font.exactMatch():
            font = QFont("Courier New", 10)

        json_wrap = QWidget()
        json_layout = QVBoxLayout(json_wrap)
        json_layout.setContentsMargins(0, 0, 0, 0)
        json_layout.setSpacing(0)
        json_layout.addWidget(self._section_label("JSON Output"))
        self._json_panel = QPlainTextEdit()
        self._json_panel.setObjectName("jsonPanel")
        self._json_panel.setReadOnly(True)
        self._json_panel.setPlaceholderText("Parsed design JSON will appear here.")
        self._json_panel.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._json_panel.setFont(font)
        json_layout.addWidget(self._json_panel, stretch=1)
        horizontal.addWidget(json_wrap)
        horizontal.setStretchFactor(0, 3)
        horizontal.setStretchFactor(1, 2)

        vertical.addWidget(horizontal)

        console_wrap = QWidget()
        console_layout = QVBoxLayout(console_wrap)
        console_layout.setContentsMargins(0, 0, 0, 0)
        console_layout.setSpacing(0)
        console_layout.addWidget(self._section_label("Console"))
        self._console = QPlainTextEdit()
        self._console.setObjectName("consolePanel")
        self._console.setReadOnly(True)
        self._console.setPlaceholderText("Parser messages will appear here.")
        self._console.setFont(font)
        self._console.setMaximumBlockCount(2000)
        console_layout.addWidget(self._console, stretch=1)
        vertical.addWidget(console_wrap)
        vertical.setStretchFactor(0, 5)
        vertical.setStretchFactor(1, 1)

        root.addWidget(vertical, stretch=1)
        self.setCentralWidget(central)

        status = QStatusBar()
        status.setSizeGripEnabled(False)
        self._status_label = QLabel("Ready")
        status.addWidget(self._status_label)
        self.setStatusBar(status)
        status.setStyleSheet(f"background-color: {t.status_bg}; color: {t.status_fg};")

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionLabel")
        return label

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&File")

        def add(menu, label: str, slot, shortcut) -> None:
            action = QAction(label, self)
            action.setShortcut(shortcut)
            # `triggered` passes a bool; the lambda drops it so any slot works.
            action.triggered.connect(lambda _checked=False, fn=slot: fn())
            menu.addAction(action)

        add(file_menu, "&Open…", self._open_dialog, QKeySequence.StandardKey.Open)
        add(file_menu, "&New", self._editor.new_file, QKeySequence.StandardKey.New)
        add(file_menu, "&Save", self._editor.save_file, QKeySequence.StandardKey.Save)
        add(file_menu, "Save &As…", self._editor.save_as, QKeySequence.StandardKey.SaveAs)
        file_menu.addSeparator()
        add(file_menu, "Save &JSON…", self.save_json, QKeySequence("Ctrl+Shift+J"))

        parse_menu = self.menuBar().addMenu("&Parse")
        add(parse_menu, "Parse &Verilog", self.parse_verilog, QKeySequence("Ctrl+P"))

    def _apply_theme(self) -> None:
        """Style only this window's own widgets.

        Selectors are scoped (object names / toolbar / menus) so the editor
        widget keeps its own look: no global ``QWidget`` rule.
        """
        t = self._theme
        self.setStyleSheet(
            f"""
            QMainWindow {{
                background-color: {t.background};
            }}
            QMenuBar {{
                background-color: {t.tab_bg};
                color: {t.tab_fg};
            }}
            QMenuBar::item:selected {{
                background-color: {t.selection};
            }}
            QMenu {{
                background-color: {t.menu_bg};
                color: {t.menu_fg};
            }}
            QMenu::item:selected {{
                background-color: {t.selection};
            }}
            QToolBar {{
                background-color: {t.tab_bg};
                border-bottom: 1px solid {t.edge};
                spacing: 8px;
                padding: 4px 8px;
            }}
            QToolBar QPushButton {{
                background-color: {t.button_bg};
                color: {t.button_fg};
                border: none;
                border-radius: 3px;
                padding: 6px 14px;
            }}
            QToolBar QPushButton:hover {{
                background-color: {t.button_hover};
            }}
            QLabel#sectionLabel {{
                color: {t.tab_fg};
                background-color: {t.tab_bg};
                padding: 6px 10px;
            }}
            QPlainTextEdit#jsonPanel, QPlainTextEdit#consolePanel {{
                background-color: {t.background};
                color: {t.foreground};
                border: 1px solid {t.edge};
                selection-background-color: {t.selection};
            }}
            QSplitter::handle {{
                background-color: {t.edge};
            }}
            QStatusBar QLabel {{
                color: {t.status_fg};
                padding: 0 8px;
            }}
            """
        )

    # -------------------------------------------------------------- actions

    def parse_verilog(self) -> None:
        source = self._editor.get_code()
        file_name = self._editor.get_current_file()
        display_name = Path(file_name).name if file_name else "Untitled"
        self._log(f"Parsing {display_name}…")

        try:
            result = self._parsing.parse_source(source, file_name=file_name)
            json_text = self._parsing.to_json_text(result)
        except Exception as exc:  # keep the GUI alive whatever happens
            self._log(f"Unexpected failure: {type(exc).__name__}: {exc}", level="ERROR")
            self._status_label.setText("Parse failed")
            return

        self._last_result = result
        self._json_panel.setPlainText(json_text)

        for diagnostic in result.diagnostics:
            self._log(
                diagnostic.message,
                level="ERROR" if diagnostic.severity == "error" else "WARN",
            )

        if result.ok:
            module_count = len(result.design.modules) if result.design else 0
            self._log(f"Parse succeeded. Modules: {module_count}.")
            self._status_label.setText("Parse succeeded")
        else:
            self._status_label.setText("Parse failed")

    def save_json(self) -> None:
        if self._last_result is None:
            QMessageBox.information(
                self,
                "Save JSON",
                "Parse Verilog first, then save the generated JSON.",
            )
            return
        current = self._editor.get_current_file()
        start = (
            str(Path(current).with_suffix(".json"))
            if current
            else str(Path.home() / "design.json")
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save JSON",
            start,
            "JSON (*.json);;All Files (*)",
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            self._parsing.save_json(self._last_result, path)
        except OSError as exc:
            QMessageBox.critical(self, "Save JSON", f"Could not save JSON:\n{exc}")
            self._log(f"Failed to save JSON: {exc}", level="ERROR")
            return
        self._log(f"Saved JSON to {path}")
        self._status_label.setText(f"Saved {Path(path).name}")

    def _log(self, message: str, *, level: str = "INFO") -> None:
        self._console.appendPlainText(f"[{level}] {message}")

    def _open_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Verilog File",
            str(Path.home()),
            "Verilog (*.v);;SystemVerilog (*.sv);;All Files (*)",
        )
        if path:
            self._editor.open_file(path)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._editor.closeEvent(event)
        if event.isAccepted():
            super().closeEvent(event)
