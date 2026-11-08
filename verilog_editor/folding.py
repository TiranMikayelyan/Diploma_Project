"""Compute Scintilla fold levels from Verilog block structure."""

from __future__ import annotations

import re

from PyQt6.Qsci import QsciScintilla

# Keywords that open / close foldable regions (case-sensitive HDL style).
_OPENERS = frozenset(
    {
        "module",
        "begin",
        "case",
        "casex",
        "casez",
        "function",
        "task",
        "generate",
        "interface",
        "package",
        "class",
        "program",
        "covergroup",
        "property",
        "sequence",
        "clocking",
        "fork",
    }
)

_CLOSERS = frozenset(
    {
        "endmodule",
        "end",
        "endcase",
        "endfunction",
        "endtask",
        "endgenerate",
        "endinterface",
        "endpackage",
        "endclass",
        "endprogram",
        "endgroup",
        "endproperty",
        "endsequence",
        "endclocking",
        "join",
        "join_any",
        "join_none",
    }
)

_WORD_RE = re.compile(r"[A-Za-z_][\w$]*|/\*|\*/|//")


def apply_verilog_folding(editor: QsciScintilla) -> None:
    """Set per-line fold levels from begin/end-style Verilog keywords."""
    lines = editor.lines()
    if lines == 0:
        return

    level = QsciScintilla.SC_FOLDLEVELBASE
    in_block_comment = False

    for i in range(lines):
        text = editor.text(i)
        header = False
        line_level = level

        # Strip strings roughly so keywords inside strings are ignored.
        scan = _strip_strings(text)
        j = 0
        while j < len(scan):
            if in_block_comment:
                end = scan.find("*/", j)
                if end < 0:
                    j = len(scan)
                    break
                in_block_comment = False
                j = end + 2
                continue

            if scan.startswith("//", j):
                break
            if scan.startswith("/*", j):
                in_block_comment = True
                j += 2
                continue

            match = _WORD_RE.match(scan, j)
            if not match:
                j += 1
                continue

            word = match.group(0)
            j = match.end()
            if word in ("/*", "*/", "//"):
                continue

            if word in _OPENERS:
                header = True
                level += 1
            elif word in _CLOSERS and level > QsciScintilla.SC_FOLDLEVELBASE:
                level -= 1
                line_level = level

        fold_flags = line_level
        if header:
            fold_flags |= QsciScintilla.SC_FOLDLEVELHEADERFLAG

        editor.SendScintilla(QsciScintilla.SCI_SETFOLDLEVEL, i, fold_flags)


def _strip_strings(line: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == '"':
            i += 1
            while i < len(line):
                if line[i] == "\\":
                    i += 2
                    continue
                if line[i] == '"':
                    i += 1
                    break
                i += 1
            out.append(" ")
            continue
        out.append(ch)
        i += 1
    return "".join(out)
