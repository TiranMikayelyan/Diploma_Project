"""Single-document QScintilla pane with Verilog editing features."""

from __future__ import annotations

from pathlib import Path

from PyQt6.Qsci import QsciScintilla
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QKeySequence, QAction, QShortcut
from PyQt6.QtWidgets import QInputDialog, QMenu

from .completer import VerilogCompleter
from .folding import apply_verilog_folding
from .lexer import VerilogLexer
from .theme import EditorTheme, DARK_THEME

SUPPORTED_EXTENSIONS = {".v", ".sv"}


class EditorPane(QsciScintilla):
    """One tab's editor surface: highlighting, folding, zoom, search helpers."""

    cursor_position_changed = pyqtSignal(int, int)  # line, column (1-based)
    modification_changed = pyqtSignal(bool)
    file_dropped = pyqtSignal(str)

    def __init__(self, parent=None, theme: EditorTheme | None = None) -> None:
        super().__init__(parent)
        self._theme = theme or DARK_THEME
        self._file_path: str | None = None
        self._completer: VerilogCompleter | None = None

        self._fold_timer = QTimer(self)
        self._fold_timer.setSingleShot(True)
        self._fold_timer.setInterval(200)
        self._fold_timer.timeout.connect(self._refresh_folding)

        self._configure_appearance()
        self._configure_behavior()
        self._configure_lexer()
        self._configure_margins()
        self._wire_signals()
        self.setAcceptDrops(True)
        self.setUtf8(True)

    # ------------------------------------------------------------------ public

    @property
    def file_path(self) -> str | None:
        return self._file_path

    @file_path.setter
    def file_path(self, path: str | None) -> None:
        self._file_path = path

    def display_name(self) -> str:
        if self._file_path:
            return Path(self._file_path).name
        return "Untitled"

    def is_modified(self) -> bool:
        return self.isModified()

    def load_from_path(self, path: str) -> None:
        path_obj = Path(path)
        text = path_obj.read_text(encoding="utf-8")
        self.setText(text)
        self._file_path = str(path_obj.resolve())
        self.setModified(False)
        self._refresh_folding()

    def save_to_path(self, path: str | None = None) -> bool:
        target = path or self._file_path
        if not target:
            return False
        Path(target).write_text(self.text(), encoding="utf-8")
        self._file_path = str(Path(target).resolve())
        self.setModified(False)
        return True

    def get_code(self) -> str:
        return self.text()

    def set_code(self, text: str) -> None:
        self.setText(text)
        self._refresh_folding()

    def clear_editor(self) -> None:
        self.clear()
        self._file_path = None
        self.setModified(False)

    # ------------------------------------------------------------------ search

    def find_text(
        self,
        text: str,
        *,
        case_sensitive: bool = False,
        whole_word: bool = False,
        forward: bool = True,
    ) -> bool:
        line, index = self.getCursorPosition()
        # When searching forward from a selection, advance past current match.
        if forward and self.hasSelectedText():
            line, index = self.getSelection()[2:4]

        found = self.findFirst(
            text,
            False,  # regexp
            case_sensitive,
            whole_word,
            True,  # wrap
            forward,
            line,
            index,
            True,  # show
            False,  # posix
        )
        return found

    def replace_current(self, find: str, replace: str, case: bool, whole: bool) -> bool:
        if self.hasSelectedText():
            selected = self.selectedText()
            cmp_sel = selected if case else selected.lower()
            cmp_find = find if case else find.lower()
            if cmp_sel == cmp_find:
                self.replaceSelectedText(replace)
                self.find_text(find, case_sensitive=case, whole_word=whole, forward=True)
                return True
        return self.find_text(find, case_sensitive=case, whole_word=whole, forward=True)

    def replace_all(self, find: str, replace: str, case: bool, whole: bool) -> int:
        if not find:
            return 0
        count = 0
        self.beginUndoAction()
        line, index = 0, 0
        while self.findFirst(
            find, False, case, whole, False, True, line, index, False, False
        ):
            self.replaceSelectedText(replace)
            count += 1
            line, index = self.getCursorPosition()
        self.endUndoAction()
        return count

    def go_to_line(self) -> None:
        max_line = max(1, self.lines())
        line, ok = QInputDialog.getInt(
            self,
            "Go to Line",
            f"Line number (1–{max_line}):",
            self.getCursorPosition()[0] + 1,
            1,
            max_line,
        )
        if ok:
            self.setCursorPosition(line - 1, 0)
            self.ensureLineVisible(line - 1)
            self.setFocus()

    # ------------------------------------------------------------------ setup

    def _configure_appearance(self) -> None:
        t = self._theme
        font = QFont("Consolas", 11)
        if not font.exactMatch():
            font = QFont("Courier New", 11)
        self.setFont(font)

        self.setPaper(QColor(t.background))
        self.setColor(QColor(t.foreground))
        self.setCaretForegroundColor(QColor(t.caret))
        self.setCaretLineVisible(True)
        self.setCaretLineBackgroundColor(QColor(t.current_line))
        self.setSelectionBackgroundColor(QColor(t.selection))
        self.setSelectionForegroundColor(QColor(t.foreground))

        self.setMatchedBraceBackgroundColor(QColor(t.matched_brace))
        self.setMatchedBraceForegroundColor(QColor("#ffffff"))
        self.setUnmatchedBraceBackgroundColor(QColor(t.unmatched_brace))
        self.setUnmatchedBraceForegroundColor(QColor("#ffffff"))
        self.setBraceMatching(QsciScintilla.BraceMatch.SloppyBraceMatch)

        self.setWhitespaceVisibility(QsciScintilla.WhitespaceVisibility.WsInvisible)
        self.setEolMode(QsciScintilla.EolMode.EolUnix)
        self.setEolVisibility(False)

    def _configure_behavior(self) -> None:
        self.setAutoIndent(True)
        self.setIndentationGuides(True)
        self.setIndentationsUseTabs(False)
        self.setTabWidth(4)
        self.setIndentationWidth(4)
        self.setBackspaceUnindents(True)
        self.setTabIndents(True)

        self.setAutoCompletionSource(QsciScintilla.AutoCompletionSource.AcsAll)
        self.setAutoCompletionThreshold(2)
        self.setAutoCompletionCaseSensitivity(False)
        self.setAutoCompletionReplaceWord(True)
        self.setAutoCompletionUseSingle(
            QsciScintilla.AutoCompletionUseSingle.AcusNever
        )

        self.SendScintilla(QsciScintilla.SCI_SETMOUSEDWELLTIME, 500)

    def _configure_lexer(self) -> None:
        lexer = VerilogLexer(self, self._theme)
        self.setLexer(lexer)
        self._completer = VerilogCompleter(lexer)

    def _configure_margins(self) -> None:
        t = self._theme
        # Margin 0 – line numbers
        self.setMarginType(0, QsciScintilla.MarginType.NumberMargin)
        self.setMarginWidth(0, "00000")
        self.setMarginLineNumbers(0, True)
        self.setMarginsBackgroundColor(QColor(t.line_number_bg))
        self.setMarginsForegroundColor(QColor(t.line_number_fg))

        # Margin 1 – unused symbol margin (kept narrow)
        self.setMarginWidth(1, 0)

        # Margin 2 – code folding
        self.setFolding(QsciScintilla.FoldStyle.BoxedTreeFoldStyle, 2)
        self.setMarginWidth(2, 14)
        self.setFoldMarginColors(QColor(t.margin_fold), QColor(t.margin_fold))

        for mark in (
            getattr(QsciScintilla, "SC_MARKNUM_FOLDEROPEN", None),
            getattr(QsciScintilla, "SC_MARKNUM_FOLDER", None),
            getattr(QsciScintilla, "SC_MARKNUM_FOLDEREND", None),
            getattr(QsciScintilla, "SC_MARKNUM_FOLDEROPENMID", None),
            getattr(QsciScintilla, "SC_MARKNUM_FOLDERMIDTAIL", None),
            getattr(QsciScintilla, "SC_MARKNUM_FOLDERSUB", None),
            getattr(QsciScintilla, "SC_MARKNUM_FOLDERTAIL", None),
        ):
            if mark is not None:
                self.setMarkerBackgroundColor(QColor(t.fold_marker), mark)
                self.setMarkerForegroundColor(QColor(t.background), mark)

    def _wire_signals(self) -> None:
        self.cursorPositionChanged.connect(self._on_cursor_moved)
        self.modificationChanged.connect(self._on_modification)
        self.textChanged.connect(self._schedule_folding)

        # Zoom with Ctrl + mouse wheel is handled in wheelEvent.
        QShortcut(QKeySequence("Ctrl+G"), self, activated=self.go_to_line)

    def _on_cursor_moved(self, line: int, index: int) -> None:
        self.cursor_position_changed.emit(line + 1, index + 1)

    def _on_modification(self, modified: bool) -> None:
        self.modification_changed.emit(modified)

    def _schedule_folding(self) -> None:
        self._fold_timer.start()

    def _refresh_folding(self) -> None:
        apply_verilog_folding(self)

    # ------------------------------------------------------------------ events

    def wheelEvent(self, event) -> None:  # noqa: N802
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.zoomIn()
            elif delta < 0:
                self.zoomOut()
            event.accept()
            return
        super().wheelEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        menu = QMenu(self)
        t = self._theme
        menu.setStyleSheet(
            f"""
            QMenu {{
                background-color: {t.menu_bg};
                color: {t.menu_fg};
                border: 1px solid {t.edge};
            }}
            QMenu::item:selected {{
                background-color: {t.selection};
            }}
            """
        )

        actions = [
            ("Undo", self.undo, QKeySequence.StandardKey.Undo),
            ("Redo", self.redo, QKeySequence.StandardKey.Redo),
            None,
            ("Cut", self.cut, QKeySequence.StandardKey.Cut),
            ("Copy", self.copy, QKeySequence.StandardKey.Copy),
            ("Paste", self.paste, QKeySequence.StandardKey.Paste),
            ("Delete", self.removeSelectedText, None),
            None,
            ("Select All", self.selectAll, QKeySequence.StandardKey.SelectAll),
            None,
            ("Go to Line…", self.go_to_line, QKeySequence("Ctrl+G")),
        ]
        for item in actions:
            if item is None:
                menu.addSeparator()
                continue
            label, slot, shortcut = item
            action = QAction(label, self)
            if shortcut is not None:
                action.setShortcut(shortcut)
            action.triggered.connect(slot)
            menu.addAction(action)

        menu.exec(event.globalPos())

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if Path(url.toLocalFile()).suffix.lower() in SUPPORTED_EXTENSIONS:
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if Path(path).suffix.lower() in SUPPORTED_EXTENSIONS:
                self.file_dropped.emit(path)
        event.acceptProposedAction()
