"""Verilog frontend built on PyVerilog's PLY (lex/yacc) parser."""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pyverilog.vparser.parser import ParseError, VerilogParser


# These patterns only pull a line/column number out of an error *message*.
# The Verilog itself is parsed by PyVerilog's grammar, never by regexes.
_COORD_RE = re.compile(r":(\d+)(?::(\d+))?:\s*(?:before|at end)", re.IGNORECASE)
_LINE_RE = re.compile(r"\bline[:\s]+(\d+)", re.IGNORECASE)
_COLUMN_RE = re.compile(r"\bcol(?:umn)?[:\s]+(\d+)", re.IGNORECASE)


@dataclass
class ParseErrorInfo:
    message: str
    line: int | None = None
    column: int | None = None


class VerilogParseError(Exception):
    def __init__(self, info: ParseErrorInfo) -> None:
        super().__init__(info.message)
        self.info = info


class VerilogSourceParser:
    """Parse Verilog source text with PyVerilog, without requiring Icarus Verilog.

    ``VerilogCodeParser.parse()`` shells out to ``iverilog`` for preprocessing.
    This class feeds source directly into PyVerilog's yacc parser so the
    application can run on machines that only have Python.

    Limitation: because there is no preprocessor, `include and `define
    directives are not expanded.
    """

    def __init__(self) -> None:
        cache_dir = Path(tempfile.gettempdir()) / "verilog_studio_ply"
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._parser = VerilogParser(outputdir=str(cache_dir), debug=False)

    def parse_text(self, source: str, file_name: str | None = None) -> Any:
        if source is None or not str(source).strip():
            raise VerilogParseError(
                ParseErrorInfo("Verilog source is empty.", line=1, column=1)
            )

        self._reset_lexer(file_name)

        try:
            ast = self._parser.parse(source, debug=0)
        except ParseError as exc:
            raise VerilogParseError(self._format_parse_error(exc, file_name)) from exc
        except Exception as exc:  # PLY may raise generic exceptions
            raise VerilogParseError(
                ParseErrorInfo(self._humanize_exception(exc, file_name))
            ) from exc

        if ast is None:
            raise VerilogParseError(
                ParseErrorInfo("Parser returned no AST. The Verilog source is invalid.")
            )
        return ast

    def _reset_lexer(self, file_name: str | None) -> None:
        """Point the lexer at the current file and restart line counting.

        PLY lexers keep ``lineno`` between parses, so without a reset the line
        numbers in the AST (and in errors) would keep growing across clicks.
        """
        lexer = getattr(self._parser, "lexer", None)
        if lexer is None:
            return
        lexer.filename = file_name or "<editor>"
        for target in (lexer, getattr(lexer, "lexer", None)):
            if target is not None and hasattr(target, "lineno"):
                try:
                    target.lineno = 1
                except (AttributeError, TypeError):
                    pass

    def _format_parse_error(
        self, exc: ParseError, file_name: str | None
    ) -> ParseErrorInfo:
        raw = str(exc).strip() or "Syntax error in Verilog source."
        line: int | None = None
        column: int | None = None
        coord = _COORD_RE.search(raw)
        if coord:
            line = int(coord.group(1))
            column = int(coord.group(2)) if coord.group(2) else None
        else:
            line = _to_int(_LINE_RE.search(raw))
            column = _to_int(_COLUMN_RE.search(raw))

        location = file_name or "<editor>"
        where = location
        if line:
            where += f" at line {line}"
            if column:
                where += f", column {column}"

        lowered = raw.lower()
        if "end of input" in lowered:
            message = (
                f"Syntax error in {location}: unexpected end of input. "
                "A module, statement, or keyword is incomplete."
            )
        elif "before:" in lowered:
            token = raw[lowered.index("before:") + len("before:"):].strip().strip("\"'")
            if token:
                message = f"Syntax error in {where}: unexpected token '{token}'."
            else:
                message = f"Syntax error in {where}."
        else:
            message = f"Syntax error in {where}: {raw}"
        return ParseErrorInfo(message=message, line=line, column=column)

    @staticmethod
    def _humanize_exception(exc: Exception, file_name: str | None) -> str:
        location = file_name or "<editor>"
        return f"Failed to parse Verilog in {location}: {exc}"


def _to_int(match: re.Match[str] | None) -> int | None:
    if match is None:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None
