"""Glue between the editor, Verilog parser, analyzer, and JSON exporter."""

from __future__ import annotations

from pathlib import Path

from models.design_model import Design, Diagnostic, ParseResult
from parser.ast_analyzer import AstAnalyzer
from parser.ast_to_json import dumps_pretty, parse_result_to_json
from parser.verilog_parser import VerilogParseError, VerilogSourceParser


class ParsingService:
    def __init__(
        self,
        parser: VerilogSourceParser | None = None,
        analyzer: AstAnalyzer | None = None,
    ) -> None:
        self._parser = parser or VerilogSourceParser()
        self._analyzer = analyzer or AstAnalyzer()

    def parse_source(self, source: str, file_name: str | None = None) -> ParseResult:
        try:
            ast = self._parser.parse_text(source, file_name=file_name)
        except VerilogParseError as exc:
            return self._failure(source, file_name, exc.info.message, exc.info.line, exc.info.column)

        try:
            design = self._analyzer.analyze(ast, source=source, file_name=file_name)
        except Exception as exc:  # never let an analyzer bug crash the GUI slot
            return self._failure(
                source,
                file_name,
                f"Internal error while analyzing the AST ({type(exc).__name__}): {exc}",
            )

        diagnostics = [
            Diagnostic(
                severity="warning",
                message=(
                    f"Module '{module.name}': {item.node_type} is not analyzed "
                    "and is missing from the JSON."
                ),
                line=item.lineno,
            )
            for module in design.modules
            for item in module.unsupported
        ]
        return ParseResult(ok=True, design=design, diagnostics=diagnostics, ast=ast)

    @staticmethod
    def _failure(
        source: str,
        file_name: str | None,
        message: str,
        line: int | None = None,
        column: int | None = None,
    ) -> ParseResult:
        return ParseResult(
            ok=False,
            design=Design(source=source, file_name=file_name, modules=[]),
            diagnostics=[Diagnostic(severity="error", message=message, line=line, column=column)],
        )

    def to_json_text(self, result: ParseResult) -> str:
        return dumps_pretty(parse_result_to_json(result))

    def save_json(self, result: ParseResult, path: str | Path) -> None:
        Path(path).write_text(self.to_json_text(result), encoding="utf-8")
