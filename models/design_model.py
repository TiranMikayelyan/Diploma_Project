"""Dataclasses that capture Verilog design hierarchy for JSON export."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


JsonDict = dict[str, Any]


def _clean(value: Any) -> Any:
    if isinstance(value, list):
        return [_clean(item) for item in value]
    if isinstance(value, dict):
        return {key: _clean(item) for key, item in value.items()}
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return value


def _expr_list(items: list[Expression | None] | None) -> list[JsonDict | None]:
    return [item.to_dict() if item else None for item in (items or [])]


@dataclass
class Expression:
    """Recursive expression tree. Missing pieces are stored as null, never invented.

    ``kind`` is one of: signal, constant, operator, concat, repeat, call,
    select (a bit/part select applied to a non-trivial base), unknown.
    """

    kind: str
    operator: str | None = None
    operands: list[Expression | None] | None = None
    signal: str | None = None
    constant: str | None = None
    index: Expression | None = None
    msb: Expression | None = None
    lsb: Expression | None = None
    part_select: str | None = None  # "+:" or "-:" for indexed part selects
    base: Expression | None = None  # only for kind == "select"
    times: Expression | None = None
    function: str | None = None
    node_type: str | None = None  # AST class name, kept for unknown expressions
    lineno: int | None = None
    unknown: bool = False

    def _select_fields(self, data: JsonDict) -> None:
        if self.index is not None:
            data["index"] = self.index.to_dict()
        if self.msb is not None:
            data["msb"] = self.msb.to_dict()
        if self.lsb is not None:
            data["lsb"] = self.lsb.to_dict()
        if self.part_select is not None:
            data["part_select"] = self.part_select

    def to_dict(self) -> JsonDict:
        data: JsonDict = {"kind": self.kind}
        if self.kind == "operator":
            data["operator"] = self.operator
            data["operands"] = _expr_list(self.operands)
        elif self.kind == "signal":
            data["signal"] = self.signal
            self._select_fields(data)
        elif self.kind == "select":
            data["base"] = self.base.to_dict() if self.base else None
            self._select_fields(data)
        elif self.kind == "constant":
            data["constant"] = self.constant
        elif self.kind == "concat":
            data["operator"] = "{}"
            data["operands"] = _expr_list(self.operands)
        elif self.kind == "repeat":
            data["operator"] = "repeat"
            data["times"] = self.times.to_dict() if self.times else None
            data["operands"] = _expr_list(self.operands)
        elif self.kind == "call":
            data["function"] = self.function
            data["operands"] = _expr_list(self.operands)
        elif self.kind == "unknown":
            data["unknown"] = True
            data["value"] = None
            data["node_type"] = self.node_type
        if self.lineno is not None:
            data["line"] = self.lineno
        return data


@dataclass
class BitRange:
    msb: int | None = None
    lsb: int | None = None
    msb_expr: Expression | None = None
    lsb_expr: Expression | None = None

    def to_dict(self) -> JsonDict:
        return {
            "msb": self.msb,
            "lsb": self.lsb,
            "msb_expr": self.msb_expr.to_dict() if self.msb_expr else None,
            "lsb_expr": self.lsb_expr.to_dict() if self.lsb_expr else None,
        }


@dataclass
class Port:
    name: str
    direction: Literal["input", "output", "inout"] | None = None
    net_type: str | None = None
    width: int | None = None
    signed: bool = False
    bit_range: BitRange | None = None
    lineno: int | None = None

    def to_dict(self) -> JsonDict:
        return {
            "name": self.name,
            "direction": self.direction,
            "net_type": self.net_type,
            "width": self.width,
            "signed": self.signed,
            "bit_range": self.bit_range.to_dict() if self.bit_range else None,
            "line": self.lineno,
        }


@dataclass
class Signal:
    name: str
    kind: str
    width: int | None = None
    signed: bool = False
    bit_range: BitRange | None = None
    dimensions: list[BitRange] = field(default_factory=list)
    initial_value: Expression | None = None
    lineno: int | None = None

    def to_dict(self) -> JsonDict:
        return {
            "name": self.name,
            "kind": self.kind,
            "width": self.width,
            "signed": self.signed,
            "bit_range": self.bit_range.to_dict() if self.bit_range else None,
            "dimensions": [item.to_dict() for item in self.dimensions],
            "initial_value": self.initial_value.to_dict() if self.initial_value else None,
            "line": self.lineno,
        }


@dataclass
class Parameter:
    name: str
    kind: Literal["parameter", "localparam"]
    value: Expression | None = None
    width: int | None = None
    signed: bool = False
    lineno: int | None = None

    def to_dict(self) -> JsonDict:
        return {
            "name": self.name,
            "kind": self.kind,
            "value": self.value.to_dict() if self.value else None,
            "width": self.width,
            "signed": self.signed,
            "line": self.lineno,
        }


@dataclass
class Assignment:
    target: Expression | None
    expression: Expression | None
    kind: Literal["continuous", "blocking", "nonblocking"]
    lineno: int | None = None

    def to_dict(self) -> JsonDict:
        return {
            "kind": self.kind,
            "target": self.target.to_dict() if self.target else None,
            "expression": self.expression.to_dict() if self.expression else None,
            "line": self.lineno,
        }


@dataclass
class Sensitivity:
    edge: str | None
    signal: str | None
    lineno: int | None = None

    def to_dict(self) -> JsonDict:
        return {"edge": self.edge, "signal": self.signal, "line": self.lineno}


@dataclass
class CaseItem:
    values: list[Expression | None]
    is_default: bool
    body: Statement | None

    def to_dict(self) -> JsonDict:
        return {
            "values": _expr_list(self.values),
            "is_default": self.is_default,
            "body": self.body.to_dict() if self.body else None,
        }


@dataclass
class Statement:
    kind: str
    condition: Expression | None = None
    then_body: Statement | None = None
    else_body: Statement | None = None
    statements: list[Statement] = field(default_factory=list)
    assignment: Assignment | None = None
    loop_init: Assignment | None = None
    loop_step: Assignment | None = None
    case_expression: Expression | None = None
    case_items: list[CaseItem] = field(default_factory=list)
    case_style: str | None = None
    node_type: str | None = None  # AST class name, kept for unknown statements
    lineno: int | None = None

    def to_dict(self) -> JsonDict:
        data: JsonDict = {"kind": self.kind, "line": self.lineno}
        if self.kind == "block":
            data["statements"] = [item.to_dict() for item in self.statements]
        elif self.kind == "if":
            data["condition"] = self.condition.to_dict() if self.condition else None
            data["then"] = self.then_body.to_dict() if self.then_body else None
            data["else"] = self.else_body.to_dict() if self.else_body else None
        elif self.kind in {"blocking_assign", "nonblocking_assign"}:
            data["assignment"] = self.assignment.to_dict() if self.assignment else None
        elif self.kind == "for":
            data["init"] = self.loop_init.to_dict() if self.loop_init else None
            data["condition"] = self.condition.to_dict() if self.condition else None
            data["step"] = self.loop_step.to_dict() if self.loop_step else None
            data["body"] = self.then_body.to_dict() if self.then_body else None
        elif self.kind in {"while", "forever"}:
            data["condition"] = self.condition.to_dict() if self.condition else None
            data["body"] = self.then_body.to_dict() if self.then_body else None
        elif self.kind == "case":
            data["style"] = self.case_style
            data["expression"] = (
                self.case_expression.to_dict() if self.case_expression else None
            )
            data["items"] = [item.to_dict() for item in self.case_items]
        elif self.kind == "unknown":
            data["unknown"] = True
            data["node_type"] = self.node_type
        return data


@dataclass
class AlwaysBlock:
    kind: str
    sensitivity: list[Sensitivity]
    body: Statement | None
    lineno: int | None = None

    def to_dict(self) -> JsonDict:
        return {
            "kind": self.kind,
            "sensitivity": [item.to_dict() for item in self.sensitivity],
            "body": self.body.to_dict() if self.body else None,
            "line": self.lineno,
        }


@dataclass
class PortConnection:
    port: str | None
    expression: Expression | None
    positional: bool = False

    def to_dict(self) -> JsonDict:
        return {
            "port": self.port,
            "expression": self.expression.to_dict() if self.expression else None,
            "positional": self.positional,
        }


@dataclass
class Instance:
    module: str
    name: str | None
    connections: list[PortConnection]
    parameters: list[PortConnection]
    lineno: int | None = None

    def to_dict(self) -> JsonDict:
        return {
            "module": self.module,
            "name": self.name,
            "connections": [item.to_dict() for item in self.connections],
            "parameters": [item.to_dict() for item in self.parameters],
            "line": self.lineno,
        }


@dataclass
class InferredClockReset:
    name: str
    role: Literal["clock", "reset"]
    reason: str
    edge: str | None = None

    def to_dict(self) -> JsonDict:
        return {
            "name": self.name,
            "role": self.role,
            "origin": "inferred",
            "reason": self.reason,
            "edge": self.edge,
        }


@dataclass
class Unsupported:
    """A module-level construct the analyzer saw but does not model."""

    node_type: str
    lineno: int | None = None
    note: str = "Construct is not analyzed; it is not represented in this JSON."

    def to_dict(self) -> JsonDict:
        return {"node_type": self.node_type, "line": self.lineno, "note": self.note}


@dataclass
class Module:
    name: str
    ports: list[Port] = field(default_factory=list)
    signals: list[Signal] = field(default_factory=list)
    parameters: list[Parameter] = field(default_factory=list)
    assignments: list[Assignment] = field(default_factory=list)
    always_blocks: list[AlwaysBlock] = field(default_factory=list)
    instances: list[Instance] = field(default_factory=list)
    inferred: dict[str, Any] = field(default_factory=dict)
    unsupported: list[Unsupported] = field(default_factory=list)
    default_nettype: str | None = None
    lineno: int | None = None

    def to_dict(self) -> JsonDict:
        return {
            "name": self.name,
            "default_nettype": self.default_nettype,
            "line": self.lineno,
            "ports": [item.to_dict() for item in self.ports],
            "signals": [item.to_dict() for item in self.signals],
            "parameters": [item.to_dict() for item in self.parameters],
            "assignments": [item.to_dict() for item in self.assignments],
            "always_blocks": [item.to_dict() for item in self.always_blocks],
            "instances": [item.to_dict() for item in self.instances],
            "inferred": _clean(self.inferred),
            "unsupported": [item.to_dict() for item in self.unsupported],
        }


@dataclass
class Design:
    modules: list[Module] = field(default_factory=list)
    source: str = ""
    file_name: str | None = None

    def to_dict(self) -> JsonDict:
        return {
            "source": self.source,
            "file_name": self.file_name,
            "modules": [item.to_dict() for item in self.modules],
        }


@dataclass
class Diagnostic:
    severity: Literal["error", "warning"]
    message: str
    line: int | None = None
    column: int | None = None

    def to_dict(self) -> JsonDict:
        return asdict(self)


@dataclass
class ParseResult:
    ok: bool
    design: Design | None
    diagnostics: list[Diagnostic] = field(default_factory=list)
    ast: Any = None

    def error_messages(self) -> list[str]:
        return [item.message for item in self.diagnostics if item.severity == "error"]
    