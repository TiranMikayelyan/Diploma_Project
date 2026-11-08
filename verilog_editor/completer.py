"""Placeholder auto-completion source for Verilog keywords and identifiers."""

from __future__ import annotations

from PyQt6.Qsci import QsciAPIs, QsciLexer


# Common Verilog / SystemVerilog completions (placeholder API list)
_PLACEHOLDER_APIS = [
    "module",
    "endmodule",
    "input",
    "output",
    "inout",
    "wire",
    "reg",
    "logic",
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
    "endcase",
    "default",
    "for",
    "while",
    "posedge",
    "negedge",
    "parameter",
    "localparam",
    "function",
    "endfunction",
    "task",
    "endtask",
    "generate",
    "endgenerate",
    "interface",
    "endinterface",
    "typedef",
    "struct",
    "enum",
    "package",
    "endpackage",
    "import",
    "$display",
    "$write",
    "$finish",
    "$stop",
    "$time",
    "$signed",
    "$unsigned",
    "$clog2",
    "$bits",
    "$readmemh",
    "$readmemb",
    "$dumpfile",
    "$dumpvars",
]


class VerilogCompleter:
    """Installs a placeholder QsciAPIs word list on a lexer."""

    def __init__(self, lexer: QsciLexer) -> None:
        self._apis = QsciAPIs(lexer)
        for api in _PLACEHOLDER_APIS:
            self._apis.add(api)
        self._apis.prepare()

    @property
    def apis(self) -> QsciAPIs:
        return self._apis
