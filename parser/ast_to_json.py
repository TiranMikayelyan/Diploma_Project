"""Convert an analyzed Verilog design (or raw AST) into JSON-serializable dicts."""

from __future__ import annotations

import json
from typing import Any

from models.design_model import Design, ParseResult
from parser.ast_analyzer import AstAnalyzer


def design_to_json(design: Design) -> dict[str, Any]:
    return {"design": design.to_dict()}


def parse_result_to_json(result: ParseResult) -> dict[str, Any]:
    return {
        "ok": result.ok,
        "design": result.design.to_dict() if result.design else None,
        "diagnostics": [item.to_dict() for item in result.diagnostics],
    }


def ast_to_json(
    ast: Any,
    source: str = "",
    file_name: str | None = None,
    analyzer: AstAnalyzer | None = None,
) -> dict[str, Any]:
    """Walk ``ast`` and return the structured JSON object."""
    model = (analyzer or AstAnalyzer()).analyze(ast, source=source, file_name=file_name)
    return design_to_json(model)


def dumps_pretty(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
