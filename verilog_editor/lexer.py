"""Verilog / SystemVerilog syntax highlighter based on QsciLexerCustom."""

from __future__ import annotations

import re

from PyQt6.Qsci import QsciLexerCustom
from PyQt6.QtGui import QColor, QFont

from .theme import EditorTheme, DARK_THEME


# Verilog / SystemVerilog keyword set
_VERILOG_KEYWORDS = frozenset(
    {
        "module",
        "endmodule",
        "input",
        "output",
        "inout",
        "wire",
        "reg",
        "logic",
        "integer",
        "real",
        "realtime",
        "time",
        "parameter",
        "localparam",
        "defparam",
        "assign",
        "always",
        "always_ff",
        "always_comb",
        "always_latch",
        "initial",
        "begin",
        "end",
        "if",
        "else",
        "case",
        "casex",
        "casez",
        "endcase",
        "default",
        "for",
        "while",
        "forever",
        "repeat",
        "wait",
        "fork",
        "join",
        "join_any",
        "join_none",
        "disable",
        "posedge",
        "negedge",
        "or",
        "and",
        "not",
        "nand",
        "nor",
        "xor",
        "xnor",
        "buf",
        "bufif0",
        "bufif1",
        "notif0",
        "notif1",
        "pulldown",
        "pullup",
        "supply0",
        "supply1",
        "tri",
        "tri0",
        "tri1",
        "triand",
        "trior",
        "trireg",
        "wand",
        "wor",
        "signed",
        "unsigned",
        "vectored",
        "scalared",
        "generate",
        "endgenerate",
        "genvar",
        "function",
        "endfunction",
        "task",
        "endtask",
        "automatic",
        "return",
        "void",
        "typedef",
        "struct",
        "union",
        "enum",
        "packed",
        "unpacked",
        "interface",
        "endinterface",
        "modport",
        "package",
        "endpackage",
        "import",
        "export",
        "class",
        "endclass",
        "extends",
        "virtual",
        "static",
        "protected",
        "local",
        "pure",
        "extern",
        "ref",
        "const",
        "context",
        "pure",
        "bit",
        "byte",
        "shortint",
        "int",
        "longint",
        "shortreal",
        "string",
        "chandle",
        "event",
        "type",
        "priority",
        "unique",
        "unique0",
        "assert",
        "assume",
        "cover",
        "property",
        "endproperty",
        "sequence",
        "endsequence",
        "clocking",
        "endclocking",
        "program",
        "endprogram",
        "covergroup",
        "endgroup",
        "rand",
        "randc",
        "constraint",
        "with",
        "inside",
        "dist",
        "solve",
        "before",
        "super",
        "this",
        "new",
        "null",
        "true",
        "false",
        "ifdef",
        "ifndef",
        "elsif",
        "endif",
        "else",
        "define",
        "undef",
        "include",
        "timescale",
        "celldefine",
        "endcelldefine",
        "default_nettype",
        "resetall",
        "pragma",
    }
)

_SYSTEM_TASKS = frozenset(
    {
        "$display",
        "$write",
        "$strobe",
        "$monitor",
        "$finish",
        "$stop",
        "$time",
        "$realtime",
        "$random",
        "$urandom",
        "$signed",
        "$unsigned",
        "$clog2",
        "$bits",
        "$size",
        "$fopen",
        "$fclose",
        "$fdisplay",
        "$fwrite",
        "$readmemb",
        "$readmemh",
        "$writememb",
        "$writememh",
        "$dumpfile",
        "$dumpvars",
        "$dumpon",
        "$dumpoff",
        "$error",
        "$warning",
        "$info",
        "$fatal",
        "$sformat",
        "$sformatf",
        "$swrite",
        "$cast",
        "$typeof",
        "$isunbounded",
    }
)


class VerilogLexer(QsciLexerCustom):
    """Custom lexer providing Verilog / SystemVerilog syntax highlighting."""

    STYLE_DEFAULT = 0
    STYLE_COMMENT = 1
    STYLE_STRING = 2
    STYLE_NUMBER = 3
    STYLE_KEYWORD = 4
    STYLE_OPERATOR = 5
    STYLE_IDENTIFIER = 6
    STYLE_PREPROCESSOR = 7
    STYLE_SYSTEM_TASK = 8

    _TOKEN_RE = re.compile(
        r"(?P<block_comment>/\*.*?\*/)"
        r"|(?P<line_comment>//[^\n]*)"
        r"|(?P<string>\"(?:\\.|[^\"\\])*\")"
        r"|(?P<preproc>`[A-Za-z_][\w$]*)"
        r"|(?P<system_task>\$[A-Za-z_][\w$]*)"
        r"|(?P<number>"
        r"(?:\d+'(?:[bB][01_xXzZ]+|[hH][0-9a-fA-F_xXzZ]+|[dD][0-9_]+|[oO][0-7_xXzZ]+))"
        r"|(?:\d+\.\d+(?:[eE][+-]?\d+)?)"
        r"|(?:\d+)"
        r")"
        r"|(?P<keyword_or_id>[A-Za-z_][\w$]*)"
        r"|(?P<operator>[\[\](){}:;,.<>!~&|^%/*+=?#@\\-])"
        r"|(?P<whitespace>\s+)"
        r"|(?P<other>.)",
        re.DOTALL,
    )

    def __init__(self, parent=None, theme: EditorTheme | None = None) -> None:
        super().__init__(parent)
        self._theme = theme or DARK_THEME
        self._configure_styles()

    def language(self) -> str:
        return "Verilog"

    def description(self, style: int) -> str:
        names = {
            self.STYLE_DEFAULT: "Default",
            self.STYLE_COMMENT: "Comment",
            self.STYLE_STRING: "String",
            self.STYLE_NUMBER: "Number",
            self.STYLE_KEYWORD: "Keyword",
            self.STYLE_OPERATOR: "Operator",
            self.STYLE_IDENTIFIER: "Identifier",
            self.STYLE_PREPROCESSOR: "Preprocessor",
            self.STYLE_SYSTEM_TASK: "System Task",
        }
        return names.get(style, "")

    def _configure_styles(self) -> None:
        theme = self._theme
        font = QFont("Consolas", 11)
        if not font.exactMatch():
            font = QFont("Courier New", 11)

        for style in range(9):
            self.setFont(font, style)
            self.setPaper(QColor(theme.background), style)
            self.setColor(QColor(theme.foreground), style)

        self.setColor(QColor(theme.comment), self.STYLE_COMMENT)
        self.setColor(QColor(theme.string), self.STYLE_STRING)
        self.setColor(QColor(theme.number), self.STYLE_NUMBER)
        self.setColor(QColor(theme.keyword), self.STYLE_KEYWORD)
        self.setColor(QColor(theme.operator), self.STYLE_OPERATOR)
        self.setColor(QColor(theme.identifier), self.STYLE_IDENTIFIER)
        self.setColor(QColor(theme.preprocessor), self.STYLE_PREPROCESSOR)
        self.setColor(QColor(theme.system_task), self.STYLE_SYSTEM_TASK)

        self.setDefaultPaper(QColor(theme.background))
        self.setDefaultColor(QColor(theme.foreground))
        self.setDefaultFont(font)

    def styleText(self, start: int, end: int) -> None:
        editor = self.editor()
        if editor is None:
            return

        # Style from the start of the document region for correct multi-line comments.
        text = editor.text()
        length = len(text)
        if length == 0:
            return

        # Re-style the whole document for correctness with block comments.
        # For typical HDL file sizes this is acceptable.
        self.startStyling(0)
        pos = 0
        while pos < length:
            match = self._TOKEN_RE.match(text, pos)
            if not match:
                self.setStyling(1, self.STYLE_DEFAULT)
                pos += 1
                continue

            group = match.lastgroup
            token = match.group(0)
            token_len = len(token.encode("utf-8"))

            if group in ("block_comment", "line_comment"):
                style = self.STYLE_COMMENT
            elif group == "string":
                style = self.STYLE_STRING
            elif group == "number":
                style = self.STYLE_NUMBER
            elif group == "preproc":
                style = self.STYLE_PREPROCESSOR
            elif group == "system_task":
                style = (
                    self.STYLE_SYSTEM_TASK
                    if token in _SYSTEM_TASKS or token.startswith("$")
                    else self.STYLE_IDENTIFIER
                )
            elif group == "keyword_or_id":
                style = (
                    self.STYLE_KEYWORD
                    if token in _VERILOG_KEYWORDS
                    else self.STYLE_IDENTIFIER
                )
            elif group == "operator":
                style = self.STYLE_OPERATOR
            else:
                style = self.STYLE_DEFAULT

            self.setStyling(token_len, style)
            pos = match.end()
