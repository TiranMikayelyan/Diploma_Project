"""Find / Replace panel for the Verilog editor."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .theme import EditorTheme, DARK_THEME


class FindReplaceBar(QWidget):
    """Inline find / replace bar (Ctrl+F / Ctrl+H)."""

    find_next = pyqtSignal(str, bool, bool)  # text, case_sensitive, whole_word
    find_previous = pyqtSignal(str, bool, bool)
    replace_one = pyqtSignal(str, str, bool, bool)  # find, replace, case, whole
    replace_all = pyqtSignal(str, str, bool, bool)
    closed = pyqtSignal()

    def __init__(self, parent=None, theme: EditorTheme | None = None) -> None:
        super().__init__(parent)
        self._theme = theme or DARK_THEME
        self._replace_visible = False
        self._build_ui()
        self._apply_theme()
        self.hide()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(4)

        find_row = QHBoxLayout()
        find_row.setSpacing(6)

        self._find_label = QLabel("Find:")
        self._find_input = QLineEdit()
        self._find_input.setPlaceholderText("Find…")
        self._find_input.returnPressed.connect(self._emit_find_next)

        self._case_cb = QCheckBox("Match case")
        self._word_cb = QCheckBox("Whole word")

        btn_next = QPushButton("Next")
        btn_next.clicked.connect(self._emit_find_next)
        btn_prev = QPushButton("Previous")
        btn_prev.clicked.connect(self._emit_find_prev)
        btn_close = QPushButton("×")
        btn_close.setFixedWidth(28)
        btn_close.setToolTip("Close (Esc)")
        btn_close.clicked.connect(self.close_bar)

        find_row.addWidget(self._find_label)
        find_row.addWidget(self._find_input, stretch=1)
        find_row.addWidget(self._case_cb)
        find_row.addWidget(self._word_cb)
        find_row.addWidget(btn_prev)
        find_row.addWidget(btn_next)
        find_row.addWidget(btn_close)
        root.addLayout(find_row)

        self._replace_row = QWidget()
        replace_layout = QHBoxLayout(self._replace_row)
        replace_layout.setContentsMargins(0, 0, 0, 0)
        replace_layout.setSpacing(6)

        self._replace_label = QLabel("Replace:")
        self._replace_input = QLineEdit()
        self._replace_input.setPlaceholderText("Replace with…")
        self._replace_input.returnPressed.connect(self._emit_replace_one)

        btn_replace = QPushButton("Replace")
        btn_replace.clicked.connect(self._emit_replace_one)
        btn_replace_all = QPushButton("Replace All")
        btn_replace_all.clicked.connect(self._emit_replace_all)

        replace_layout.addWidget(self._replace_label)
        replace_layout.addWidget(self._replace_input, stretch=1)
        replace_layout.addWidget(btn_replace)
        replace_layout.addWidget(btn_replace_all)
        root.addWidget(self._replace_row)
        self._replace_row.hide()

        esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc.activated.connect(self.close_bar)

    def _apply_theme(self) -> None:
        t = self._theme
        self.setStyleSheet(
            f"""
            FindReplaceBar {{
                background-color: {t.find_bg};
                border-bottom: 1px solid {t.find_border};
            }}
            QLabel {{
                color: {t.find_input_fg};
            }}
            QLineEdit {{
                background-color: {t.find_input_bg};
                color: {t.find_input_fg};
                border: 1px solid {t.find_border};
                border-radius: 3px;
                padding: 3px 6px;
                selection-background-color: {t.selection};
            }}
            QCheckBox {{
                color: {t.find_input_fg};
            }}
            QPushButton {{
                background-color: {t.button_bg};
                color: {t.button_fg};
                border: none;
                border-radius: 3px;
                padding: 4px 10px;
            }}
            QPushButton:hover {{
                background-color: {t.button_hover};
            }}
            """
        )

    def show_find(self, selected_text: str = "") -> None:
        self._replace_visible = False
        self._replace_row.hide()
        if selected_text:
            self._find_input.setText(selected_text)
        self.show()
        self._find_input.setFocus()
        self._find_input.selectAll()

    def show_replace(self, selected_text: str = "") -> None:
        self._replace_visible = True
        self._replace_row.show()
        if selected_text:
            self._find_input.setText(selected_text)
        self.show()
        self._find_input.setFocus()
        self._find_input.selectAll()

    def close_bar(self) -> None:
        self.hide()
        self.closed.emit()

    def _flags(self) -> tuple[bool, bool]:
        return self._case_cb.isChecked(), self._word_cb.isChecked()

    def _emit_find_next(self) -> None:
        text = self._find_input.text()
        if text:
            case, word = self._flags()
            self.find_next.emit(text, case, word)

    def _emit_find_prev(self) -> None:
        text = self._find_input.text()
        if text:
            case, word = self._flags()
            self.find_previous.emit(text, case, word)

    def _emit_replace_one(self) -> None:
        find = self._find_input.text()
        if find:
            case, word = self._flags()
            self.replace_one.emit(find, self._replace_input.text(), case, word)

    def _emit_replace_all(self) -> None:
        find = self._find_input.text()
        if find:
            case, word = self._flags()
            self.replace_all.emit(find, self._replace_input.text(), case, word)
