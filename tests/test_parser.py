"""Unit tests for the PyVerilog-based parser, analyzer, and JSON exporter."""

from __future__ import annotations

import json

import pytest
from pyverilog.vparser import ast as vast

from models.design_model import Module, Port
from parser.ast_analyzer import AstAnalyzer, is_clock_name, is_reset_name
from services.parsing_service import ParsingService


ADDER = """
module adder(
  input [3:0] a,
  input [3:0] b,
  output [4:0] sum
);
  assign sum = a + b;
endmodule
"""

MUX = """
module mux2(
  input [7:0] a,
  input [7:0] b,
  input sel,
  output [7:0] y
);
  assign y = sel ? b : a;
endmodule
"""

COUNTER = """
module counter(
  input clk,
  input rst,
  output reg [3:0] q
);
  always @(posedge clk or posedge rst) begin
    if (rst)
      q <= 4'b0000;
    else
      q <= q + 1'b1;
  end
endmodule
"""

REGISTER = """
module dff_reset(
  input clk,
  input rst,
  input d,
  output reg q
);
  always @(posedge clk) begin
    if (rst)
      q <= 1'b0;
    else
      q <= d;
  end
endmodule
"""

MULTI = """
module inv(input a, output y);
  assign y = ~a;
endmodule

module top(input a, output y);
  inv u0(.a(a), .y(y));
endmodule
"""

# `localparam` goes in the module body: it is not valid inside `#( ... )` in
# plain Verilog-2001, which is what PyVerilog's grammar implements.
PARAMETERIZED = """
module param_adder #(
  parameter WIDTH = 8
) (
  input [WIDTH-1:0] a,
  input [WIDTH-1:0] b,
  output [WIDTH:0] sum
);
  localparam EXTRA = 1;
  assign sum = a + b;
endmodule
"""

NESTED_IF = """
module nested_if(
  input a,
  input b,
  input c,
  output reg y
);
  always @(*) begin
    if (a) begin
      if (b)
        y = 1'b1;
      else
        y = 1'b0;
    end else
      y = c;
  end
endmodule
"""

CASE_STMT = """
module alu(
  input [1:0] op,
  input [3:0] a,
  input [3:0] b,
  output reg [3:0] y
);
  always @(*) begin
    case (op)
      2'b00: y = a + b;
      2'b01: y = a - b;
      2'b10: y = a & b;
      default: y = a | b;
    endcase
  end
endmodule
"""

INVALID = """
module broken(input a
  assign a = 1;
"""

WIDTHS = """
module widths(
  input a,
  input [7:0] b,
  input [15:8] c,
  output [3:0] d
);
  wire [1:0] w;
  reg [31:0] r;
  integer k;
  assign d = b[3:0];
endmodule
"""

NON_ANSI = """
module legacy(a, y);
  input [1:0] a;
  output reg y;
  always @(*) y = a[0];
endmodule
"""

INITIAL_BLOCK = """
module init_block(output reg q);
  initial begin
    q = 1'b0;
  end
endmodule
"""


@pytest.fixture(scope="module")
def service() -> ParsingService:
    return ParsingService()


def _module(result, name: str | None = None):
    assert result.ok, result.error_messages()
    assert result.design is not None
    if name is None:
        return result.design.modules[0]
    matches = [item for item in result.design.modules if item.name == name]
    assert matches, f"module {name} not found"
    return matches[0]


def _json(service: ParsingService, result) -> dict:
    return json.loads(service.to_json_text(result))


def test_simple_adder(service: ParsingService) -> None:
    result = service.parse_source(ADDER, file_name="adder.v")
    module = _module(result, "adder")
    ports = {port.name: port for port in module.ports}
    assert ports["a"].direction == "input"
    assert ports["a"].width == 4
    assert ports["b"].width == 4
    assert ports["sum"].direction == "output"
    assert ports["sum"].width == 5
    assert len(module.assignments) == 1
    assignment = module.assignments[0]
    assert assignment.kind == "continuous"
    assert assignment.target.signal == "sum"
    assert assignment.expression.operator == "+"
    assert [op.signal for op in assignment.expression.operands] == ["a", "b"]
    payload = _json(service, result)
    json.dumps(payload)
    names = [item["name"] for item in payload["design"]["modules"]]
    assert names == ["adder"]


def test_multiplexer(service: ParsingService) -> None:
    result = service.parse_source(MUX, file_name="mux.v")
    module = _module(result, "mux2")
    assignment = module.assignments[0]
    assert assignment.expression.operator == "?:"
    assert assignment.expression.operands[0].signal == "sel"
    assert assignment.expression.operands[1].signal == "b"
    assert assignment.expression.operands[2].signal == "a"
    assert {port.name: port.width for port in module.ports}["y"] == 8


def test_counter(service: ParsingService) -> None:
    result = service.parse_source(COUNTER, file_name="counter.v")
    module = _module(result, "counter")
    assert len(module.always_blocks) == 1
    block = module.always_blocks[0]
    edges = {(item.edge, item.signal) for item in block.sensitivity}
    assert ("posedge", "clk") in edges
    assert ("posedge", "rst") in edges
    body = block.body
    assert body.kind == "block"
    inner = body.statements[0]
    assert inner.kind == "if"
    assert inner.then_body.assignment.kind == "nonblocking"
    assert inner.else_body.assignment.kind == "nonblocking"
    clocks = [item["name"] for item in module.inferred["clock_signals"]]
    resets = [item["name"] for item in module.inferred["reset_signals"]]
    assert "clk" in clocks
    assert "rst" in resets
    q = next(port for port in module.ports if port.name == "q")
    assert q.net_type == "reg"
    assert q.width == 4


def test_register_with_reset(service: ParsingService) -> None:
    result = service.parse_source(REGISTER, file_name="dff.v")
    module = _module(result, "dff_reset")
    q = next(port for port in module.ports if port.name == "q")
    assert q.direction == "output"
    assert q.net_type == "reg"
    assert q.width == 1
    always = module.always_blocks[0]
    assert always.sensitivity[0].signal == "clk"
    assert always.body.statements[0].kind == "if"
    clocks = [item["name"] for item in module.inferred["clock_signals"]]
    resets = [item["name"] for item in module.inferred["reset_signals"]]
    assert "clk" in clocks
    assert "rst" in resets


def test_multiple_modules(service: ParsingService) -> None:
    result = service.parse_source(MULTI, file_name="multi.v")
    assert result.ok
    names = [module.name for module in result.design.modules]
    assert names == ["inv", "top"]
    top = _module(result, "top")
    assert len(top.instances) == 1
    inst = top.instances[0]
    assert inst.module == "inv"
    assert inst.name == "u0"
    connected = {conn.port: conn.expression.signal for conn in inst.connections}
    assert connected == {"a": "a", "y": "y"}
    payload = _json(service, result)
    assert [item["name"] for item in payload["design"]["modules"]] == ["inv", "top"]


def test_parameterized_module(service: ParsingService) -> None:
    result = service.parse_source(PARAMETERIZED, file_name="param.v")
    module = _module(result, "param_adder")
    params = {item.name: item for item in module.parameters}
    assert "WIDTH" in params
    assert params["WIDTH"].kind == "parameter"
    assert params["WIDTH"].value.constant == "8"
    assert params["WIDTH"].width is None  # no declared range: not invented
    assert params["EXTRA"].kind == "localparam"
    a = next(port for port in module.ports if port.name == "a")
    assert a.width is None
    assert a.bit_range is not None
    assert a.bit_range.msb is None
    assert a.bit_range.msb_expr is not None
    assert a.bit_range.msb_expr.operator == "-"


def test_nested_if_else(service: ParsingService) -> None:
    result = service.parse_source(NESTED_IF, file_name="nested.v")
    module = _module(result, "nested_if")
    if_stmt = module.always_blocks[0].body.statements[0]
    assert if_stmt.kind == "if"
    nested = if_stmt.then_body
    if nested.kind == "block":
        nested = nested.statements[0]
    assert nested.kind == "if"
    assert nested.then_body.kind == "blocking_assign"
    assert nested.else_body.kind == "blocking_assign"
    assert if_stmt.else_body.kind == "blocking_assign"


def test_case_statement(service: ParsingService) -> None:
    result = service.parse_source(CASE_STMT, file_name="alu.v")
    module = _module(result, "alu")
    case = module.always_blocks[0].body.statements[0]
    assert case.kind == "case"
    assert case.case_style == "case"
    assert case.case_expression.signal == "op"
    assert len(case.case_items) == 4
    assert case.case_items[-1].is_default is True
    first = case.case_items[0].body
    assert first.assignment.expression.operator == "+"
    third = case.case_items[2].body
    assert third.assignment.expression.operator == "&"


def test_invalid_syntax(service: ParsingService) -> None:
    result = service.parse_source(INVALID, file_name="bad.v")
    assert result.ok is False
    assert result.diagnostics
    message = result.diagnostics[0].message.lower()
    assert "syntax" in message or "error" in message
    payload = _json(service, result)
    assert payload["ok"] is False
    assert payload["diagnostics"][0]["severity"] == "error"


def test_different_signal_widths(service: ParsingService) -> None:
    result = service.parse_source(WIDTHS, file_name="widths.v")
    module = _module(result, "widths")
    ports = {port.name: port for port in module.ports}
    assert ports["a"].width == 1
    assert ports["b"].width == 8
    assert ports["c"].width == 8
    assert ports["c"].bit_range.msb == 15
    assert ports["c"].bit_range.lsb == 8
    assert ports["d"].width == 4
    signals = {sig.name: sig for sig in module.signals}
    assert signals["w"].kind == "wire"
    assert signals["w"].width == 2
    assert signals["r"].kind == "reg"
    assert signals["r"].width == 32
    assert signals["k"].kind == "integer"
    assert signals["k"].width is None  # integer size is not stated in the source
    assign = module.assignments[0]
    assert assign.expression.signal == "b"
    assert assign.expression.msb.constant == "3"
    assert assign.expression.lsb.constant == "0"


def test_source_is_preserved(service: ParsingService) -> None:
    result = service.parse_source(ADDER, file_name="adder.v")
    assert result.design.source == ADDER
    assert result.design.file_name == "adder.v"


def test_empty_source_is_an_error(service: ParsingService) -> None:
    result = service.parse_source("   \n", file_name="empty.v")
    assert result.ok is False
    assert "empty" in result.diagnostics[0].message.lower()


def test_non_ansi_ports(service: ParsingService) -> None:
    result = service.parse_source(NON_ANSI, file_name="legacy.v")
    module = _module(result, "legacy")
    ports = {port.name: port for port in module.ports}
    assert ports["a"].direction == "input"
    assert ports["a"].width == 2
    assert ports["y"].direction == "output"
    assert ports["y"].net_type == "reg"
    assert ports["y"].width == 1


def test_unsupported_constructs_are_reported_not_dropped(service: ParsingService) -> None:
    result = service.parse_source(INITIAL_BLOCK, file_name="init.v")
    module = _module(result, "init_block")
    assert any(item.node_type == "Initial" for item in module.unsupported)
    assert any(item.severity == "warning" for item in result.diagnostics)
    payload = _json(service, result)
    assert payload["design"]["modules"][0]["unsupported"]


def test_line_numbers_do_not_accumulate_between_parses(service: ParsingService) -> None:
    first = service.parse_source(ADDER, file_name="adder.v")
    second = service.parse_source(ADDER, file_name="adder.v")
    assert _module(first).lineno == _module(second).lineno


def test_clock_and_reset_names_match_whole_tokens() -> None:
    assert is_clock_name("clk")
    assert is_clock_name("sys_clk")
    assert is_clock_name("clk_i")
    assert is_reset_name("rst_n")
    assert is_reset_name("aresetn")
    assert not is_reset_name("first")
    assert not is_reset_name("burst")
    assert is_clock_name("clock")
    assert not is_clock_name("blocked")


def test_inference_is_marked_as_inferred() -> None:
    module = Module(
        name="m",
        ports=[
            Port(name="clk_i", direction="input"),
            Port(name="rst_n", direction="input"),
            Port(name="first", direction="input"),
        ],
    )
    inferred = AstAnalyzer()._infer_clock_reset(module)
    assert [item["name"] for item in inferred["clock_signals"]] == ["clk_i"]
    assert [item["name"] for item in inferred["reset_signals"]] == ["rst_n"]
    assert all(item["origin"] == "inferred" for item in inferred["clock_signals"])


def test_nested_index_keeps_both_indices() -> None:
    # mem[1][2] -> the inner index must not be overwritten by the outer one.
    node = vast.Pointer(
        vast.Pointer(vast.Identifier("mem"), vast.IntConst("1")),
        vast.IntConst("2"),
    )
    expr = AstAnalyzer().expression(node)
    assert expr.kind == "select"
    assert expr.index.constant == "2"
    assert expr.base.signal == "mem"
    assert expr.base.index.constant == "1"


def test_indexed_part_select_is_not_unknown() -> None:
    if not hasattr(vast, "PartselectPlus"):
        pytest.skip("this PyVerilog version has no PartselectPlus")
    node = vast.PartselectPlus(
        vast.Identifier("a"), vast.Identifier("i"), vast.IntConst("4")
    )
    expr = AstAnalyzer().expression(node)
    assert expr.kind == "signal"
    assert expr.signal == "a"
    assert expr.part_select == "+:"
    assert expr.msb.signal == "i"
    assert expr.lsb.constant == "4"
