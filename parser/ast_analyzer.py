"""Walk a PyVerilog AST and build a hierarchical design model."""

from __future__ import annotations

import re
from typing import Any

from pyverilog.vparser import ast as vast

from models.design_model import (
    AlwaysBlock,
    Assignment,
    BitRange,
    CaseItem,
    Design,
    Expression,
    InferredClockReset,
    Instance,
    Module,
    Parameter,
    Port,
    PortConnection,
    Sensitivity,
    Signal,
    Statement,
    Unsupported,
)


# Clock / reset recognition works on "_"-separated name tokens, so ``rst_n`` and
# ``sys_clk`` match but ``first`` or ``burst`` do not.
_CLOCK_TOKENS = frozenset({"clk", "clock", "sysclk"})
_RESET_TOKENS = frozenset(
    {
        "rst",
        "reset",
        "rstn",
        "resetn",
        "arst",
        "arstn",
        "areset",
        "aresetn",
        "nrst",
        "nreset",
        "rstni",
    }
)
_UNSIZED_KINDS = frozenset({"Integer", "Real", "Genvar"})
_INT_RE = re.compile(r"^[+-]?\d+$")
_BASED_INT_RE = re.compile(r"^(?:\d+)?'[sS]?([bBoOdDhH])([0-9a-fA-FxXzZ]+)$")

_OPERATOR_SYMBOLS = {
    "Plus": "+",
    "Minus": "-",
    "Times": "*",
    "Divide": "/",
    "Mod": "%",
    "Power": "**",
    "Sll": "<<",
    "Srl": ">>",
    "Sla": "<<<",
    "Sra": ">>>",
    "LessThan": "<",
    "GreaterThan": ">",
    "LessEq": "<=",
    "GreaterEq": ">=",
    "Eq": "==",
    "NotEq": "!=",
    "Eql": "===",
    "NotEql": "!==",
    "And": "&",
    "Xor": "^",
    "Xnor": "^~",
    "Or": "|",
    "Land": "&&",
    "Lor": "||",
    "Uplus": "+",
    "Uminus": "-",
    "Ulnot": "!",
    "Unot": "~",
    "Uand": "&",
    "Unand": "~&",
    "Uor": "|",
    "Unor": "~|",
    "Uxor": "^",
    "Uxnor": "~^",
}
# Built with getattr so a PyVerilog version that lacks one class still imports.
_OPERATORS = {
    getattr(vast, name): symbol
    for name, symbol in _OPERATOR_SYMBOLS.items()
    if hasattr(vast, name)
}


def _is(node: Any, *names: str) -> bool:
    """isinstance() against PyVerilog classes by name; missing classes never match."""
    for name in names:
        cls = getattr(vast, name, None)
        if isinstance(cls, type) and isinstance(node, cls):
            return True
    return False


def _name_tokens(name: str) -> list[str]:
    tokens = []
    for part in name.lower().split("_"):
        part = part.rstrip("0123456789") or part
        if part:
            tokens.append(part)
    return tokens


def is_clock_name(name: str) -> bool:
    return any(token in _CLOCK_TOKENS for token in _name_tokens(name))


def is_reset_name(name: str) -> bool:
    return any(token in _RESET_TOKENS for token in _name_tokens(name))


class AstAnalyzer:
    """Convert a PyVerilog ``Source`` AST into :class:`Design`."""

    def analyze(self, ast: vast.Node, source: str = "", file_name: str | None = None) -> Design:
        modules: list[Module] = []
        description = getattr(ast, "description", None)
        definitions = getattr(description, "definitions", ()) if description else ()
        for definition in definitions or ():
            if isinstance(definition, vast.ModuleDef):
                modules.append(self._analyze_module(definition))
        return Design(modules=modules, source=source, file_name=file_name)

    # ------------------------------------------------------------------ modules

    def _analyze_module(self, node: vast.ModuleDef) -> Module:
        module = Module(
            name=node.name,
            default_nettype=getattr(node, "default_nettype", None),
            lineno=getattr(node, "lineno", None),
        )
        ports: dict[str, Port] = {}
        self._collect_port_headers(node.portlist, ports)

        if node.paramlist is not None:
            for item in node.paramlist.params or ():
                self._ingest_decl_item(item, module, ports)

        for item in node.items or ():
            self._ingest_item(item, module, ports)

        # A declared port with no explicit range is one bit wide. Ports that were
        # only listed in the header and never declared stay unknown (null).
        for port in ports.values():
            if port.direction is not None and port.width is None and port.bit_range is None:
                port.width = 1

        module.ports = list(ports.values())
        module.inferred = self._infer_clock_reset(module)
        return module

    def _collect_port_headers(
        self, portlist: vast.Portlist | None, ports: dict[str, Port]
    ) -> None:
        if portlist is None:
            return
        for item in portlist.ports or ():
            if isinstance(item, vast.Ioport):
                self._apply_direction(item.first, ports)
                if item.second is not None:
                    self._apply_net(item.second, ports)
            elif isinstance(item, vast.Port):
                port = ports.setdefault(
                    item.name, Port(name=item.name, lineno=getattr(item, "lineno", None))
                )
                self._merge_width(port, getattr(item, "width", None))
                item_type = getattr(item, "type", None)
                if item_type:
                    port.net_type = str(item_type)

    def _ingest_item(self, item: vast.Node, module: Module, ports: dict[str, Port]) -> None:
        if isinstance(item, vast.Decl):
            for decl in item.list or ():
                self._ingest_decl_item(decl, module, ports)
        elif _is(item, "Paramlist"):
            for decl in item.params or ():
                self._ingest_decl_item(decl, module, ports)
        elif isinstance(item, vast.Parameter):  # also covers Localparam
            module.parameters.append(self._parameter(item))
        elif isinstance(item, vast.Assign):
            module.assignments.append(self._continuous(item))
        elif isinstance(item, vast.Always):
            module.always_blocks.append(self._always(item))
        elif isinstance(item, vast.InstanceList):
            for instance in item.instances or ():
                module.instances.append(self._instance(instance, item))
        elif isinstance(item, vast.Instance):
            module.instances.append(self._instance(item, None))
        elif _is(item, "GenerateStatement"):
            for child in item.items or ():
                self._ingest_item(child, module, ports)
        elif isinstance(item, vast.Block):
            for child in item.statements or ():
                self._ingest_item(child, module, ports)
        else:
            self._note_unsupported(item, module)

    def _ingest_decl_item(
        self, decl: vast.Node, module: Module, ports: dict[str, Port]
    ) -> None:
        if isinstance(decl, vast.Decl):
            for nested in decl.list or ():
                self._ingest_decl_item(nested, module, ports)
        elif isinstance(decl, vast.Parameter):  # also covers Localparam
            module.parameters.append(self._parameter(decl))
        elif isinstance(decl, (vast.Input, vast.Output, vast.Inout)):
            self._apply_direction(decl, ports)
        elif isinstance(decl, vast.Assign):  # e.g. `wire w = a & b;`
            module.assignments.append(self._continuous(decl))
        elif _is(decl, "Variable", "Wire", "Reg", "Integer", "Real", "Genvar", "Tri"):
            if decl.name in ports:
                self._apply_net(decl, ports)
            else:
                module.signals.append(self._signal(decl))
        else:
            self._note_unsupported(decl, module)

    @staticmethod
    def _note_unsupported(node: Any, module: Module) -> None:
        module.unsupported.append(
            Unsupported(node_type=type(node).__name__, lineno=getattr(node, "lineno", None))
        )

    # ------------------------------------------------------------------- ports

    def _port_for(self, node: vast.Node, ports: dict[str, Port]) -> Port:
        return ports.setdefault(
            node.name, Port(name=node.name, lineno=getattr(node, "lineno", None))
        )

    def _merge_width(self, port: Port, width_node: vast.Node | None) -> None:
        """Take a width from ``width_node`` only when the declaration has one."""
        if width_node is None:
            return
        width, bit_range = self._width_of(width_node)
        port.width = width
        port.bit_range = bit_range

    def _apply_direction(self, node: vast.Node | None, ports: dict[str, Port]) -> None:
        if node is None or not hasattr(node, "name"):
            return
        port = self._port_for(node, ports)
        if isinstance(node, vast.Input):
            port.direction = "input"
        elif isinstance(node, vast.Output):
            port.direction = "output"
        elif isinstance(node, vast.Inout):
            port.direction = "inout"
        self._merge_width(port, getattr(node, "width", None))
        if getattr(node, "signed", False):
            port.signed = True

    def _apply_net(self, node: vast.Node | None, ports: dict[str, Port]) -> None:
        """Apply a wire/reg/... declaration to a port (``output reg q``)."""
        if node is None or not hasattr(node, "name"):
            return
        port = self._port_for(node, ports)
        port.net_type = type(node).__name__.lower()
        self._merge_width(port, getattr(node, "width", None))
        if getattr(node, "signed", False):
            port.signed = True

    # ----------------------------------------------------- signals, parameters

    def _signal(self, node: vast.Node) -> Signal:
        width_node = getattr(node, "width", None)
        if width_node is not None:
            width, bit_range = self._width_of(width_node)
        elif type(node).__name__ in _UNSIZED_KINDS:
            width, bit_range = None, None
        else:
            width, bit_range = 1, None

        dimensions: list[BitRange] = []
        dims = getattr(node, "dimensions", None)
        if dims is not None:
            for length in getattr(dims, "lengths", None) or ():
                _, dim_range = self._width_of(length)
                if dim_range is not None:
                    dimensions.append(dim_range)

        initial = getattr(node, "value", None)
        return Signal(
            name=node.name,
            kind=type(node).__name__.lower(),
            width=width,
            signed=bool(getattr(node, "signed", False)),
            bit_range=bit_range,
            dimensions=dimensions,
            initial_value=self.expression(initial) if initial is not None else None,
            lineno=getattr(node, "lineno", None),
        )

    def _parameter(self, node: vast.Parameter) -> Parameter:
        width, _ = self._width_of(getattr(node, "width", None))
        kind = "localparam" if _is(node, "Localparam") else "parameter"
        return Parameter(
            name=node.name,
            kind=kind,
            value=self.expression(getattr(node, "value", None)),
            width=width,
            signed=bool(getattr(node, "signed", False)),
            lineno=getattr(node, "lineno", None),
        )

    # ------------------------------------------------------------- behaviour

    def _continuous(self, node: vast.Assign) -> Assignment:
        return self._assignment(node, "continuous")

    def _assignment(self, node: Any, kind: str) -> Assignment:
        return Assignment(
            target=self.expression(node.left),
            expression=self.expression(node.right),
            kind=kind,  # type: ignore[arg-type]
            lineno=getattr(node, "lineno", None),
        )

    def _always(self, node: vast.Always) -> AlwaysBlock:
        kind = "always"
        if _is(node, "AlwaysFF"):
            kind = "always_ff"
        elif _is(node, "AlwaysComb"):
            kind = "always_comb"
        elif _is(node, "AlwaysLatch"):
            kind = "always_latch"
        sensitivity: list[Sensitivity] = []
        sens_list = getattr(node, "sens_list", None)
        if sens_list is not None:
            for sens in sens_list.list or ():
                if isinstance(sens, vast.Sens):
                    signal_name = None
                    if isinstance(sens.sig, vast.Identifier):
                        signal_name = sens.sig.name
                    elif sens.sig is not None:
                        expr = self.expression(sens.sig)
                        signal_name = expr.signal if expr and expr.signal else None
                    sensitivity.append(
                        Sensitivity(
                            edge=sens.type,
                            signal=signal_name,
                            lineno=getattr(sens, "lineno", None),
                        )
                    )
        return AlwaysBlock(
            kind=kind,
            sensitivity=sensitivity,
            body=self.statement(node.statement),
            lineno=getattr(node, "lineno", None),
        )

    def _instance(self, node: vast.Instance, parent: vast.InstanceList | None) -> Instance:
        module_name = node.module or (parent.module if parent else None)
        param_source = node.parameterlist or (parent.parameterlist if parent else None)
        return Instance(
            module=module_name or "",
            name=node.name,
            connections=[self._port_arg(arg) for arg in node.portlist or ()],
            parameters=[self._param_arg(arg) for arg in param_source or ()],
            lineno=getattr(node, "lineno", None),
        )

    def _port_arg(self, arg: vast.PortArg | vast.Node) -> PortConnection:
        if isinstance(arg, vast.PortArg):
            return PortConnection(
                port=arg.portname,
                expression=self.expression(arg.argname) if arg.argname is not None else None,
                positional=arg.portname is None,
            )
        return PortConnection(port=None, expression=self.expression(arg), positional=True)

    def _param_arg(self, arg: vast.ParamArg | vast.Node) -> PortConnection:
        if isinstance(arg, vast.ParamArg):
            return PortConnection(
                port=arg.paramname,
                expression=self.expression(arg.argname) if arg.argname is not None else None,
                positional=arg.paramname is None,
            )
        return PortConnection(port=None, expression=self.expression(arg), positional=True)

    def statement(self, node: vast.Node | None) -> Statement | None:
        if node is None:
            return None
        lineno = getattr(node, "lineno", None)
        if isinstance(node, vast.Block):
            children = (self.statement(child) for child in node.statements or ())
            return Statement(
                kind="block",
                statements=[child for child in children if child is not None],
                lineno=lineno,
            )
        if isinstance(node, vast.IfStatement):
            return Statement(
                kind="if",
                condition=self.expression(node.cond),
                then_body=self.statement(node.true_statement),
                else_body=self.statement(node.false_statement),
                lineno=lineno,
            )
        if isinstance(node, vast.BlockingSubstitution):
            return Statement(
                kind="blocking_assign",
                assignment=self._assignment(node, "blocking"),
                lineno=lineno,
            )
        if isinstance(node, vast.NonblockingSubstitution):
            return Statement(
                kind="nonblocking_assign",
                assignment=self._assignment(node, "nonblocking"),
                lineno=lineno,
            )
        if isinstance(node, vast.ForStatement):
            return Statement(
                kind="for",
                loop_init=self._substitution(node.pre),
                condition=self.expression(node.cond),
                loop_step=self._substitution(node.post),
                then_body=self.statement(node.statement),
                lineno=lineno,
            )
        if isinstance(node, vast.WhileStatement):
            return Statement(
                kind="while",
                condition=self.expression(node.cond),
                then_body=self.statement(node.statement),
                lineno=lineno,
            )
        if _is(node, "ForeverStatement"):
            return Statement(
                kind="forever",
                then_body=self.statement(node.statement),
                lineno=lineno,
            )
        if isinstance(node, vast.CaseStatement):
            return self._case(node, lineno)
        return Statement(kind="unknown", node_type=type(node).__name__, lineno=lineno)

    def _case(self, node: vast.CaseStatement, lineno: int | None) -> Statement:
        style = "case"
        if _is(node, "CasexStatement"):
            style = "casex"
        elif _is(node, "CasezStatement"):
            style = "casez"
        elif _is(node, "UniqueCaseStatement"):
            style = "unique_case"
        items: list[CaseItem] = []
        for case in node.caselist or ():
            if not isinstance(case, vast.Case):
                continue
            conds = case.cond
            if conds is None:
                values: list[Expression | None] = []
            elif isinstance(conds, (list, tuple)):
                values = [self.expression(value) for value in conds]
            else:
                values = [self.expression(conds)]
            items.append(
                CaseItem(
                    values=values,
                    is_default=conds is None,
                    body=self.statement(case.statement),
                )
            )
        return Statement(
            kind="case",
            case_style=style,
            case_expression=self.expression(node.comp),
            case_items=items,
            lineno=lineno,
        )

    def _substitution(self, node: vast.Node | None) -> Assignment | None:
        if isinstance(node, vast.BlockingSubstitution):
            return self._assignment(node, "blocking")
        if isinstance(node, vast.NonblockingSubstitution):
            return self._assignment(node, "nonblocking")
        return None

    # ------------------------------------------------------------ expressions

    def expression(self, node: vast.Node | None) -> Expression | None:
        node = self._unwrap(node)
        if node is None:
            return None
        lineno = getattr(node, "lineno", None)

        if isinstance(node, vast.Identifier):
            return Expression(kind="signal", signal=node.name, lineno=lineno)
        if _is(node, "IntConst", "FloatConst", "StringConst"):
            return Expression(kind="constant", constant=str(node.value), lineno=lineno)
        # PartselectPlus/Minus subclass Partselect, so test them first.
        if _is(node, "PartselectPlus"):
            return self._select(node, lineno, "plus")
        if _is(node, "PartselectMinus"):
            return self._select(node, lineno, "minus")
        if _is(node, "Partselect"):
            return self._select(node, lineno, "range")
        if _is(node, "Pointer"):
            return self._select(node, lineno, "index")
        if _is(node, "Concat", "LConcat"):
            return Expression(
                kind="concat",
                operator="{}",
                operands=[self.expression(item) for item in node.list or ()],
                lineno=lineno,
            )
        if _is(node, "Repeat"):
            return Expression(
                kind="repeat",
                operator="repeat",
                times=self.expression(node.times),
                operands=[self.expression(node.value)],
                lineno=lineno,
            )
        if _is(node, "Cond"):
            return Expression(
                kind="operator",
                operator="?:",
                operands=[
                    self.expression(node.cond),
                    self.expression(node.true_value),
                    self.expression(node.false_value),
                ],
                lineno=lineno,
            )
        if _is(node, "FunctionCall"):
            return Expression(
                kind="call",
                function=self._name_of(node.name) or "unknown",
                operands=[self.expression(arg) for arg in node.args or ()],
                lineno=lineno,
            )
        if _is(node, "SystemCall"):
            name = str(node.syscall)
            return Expression(
                kind="call",
                function=name if name.startswith("$") else f"${name}",
                operands=[self.expression(arg) for arg in node.args or ()],
                lineno=lineno,
            )
        if _is(node, "UnaryOperator"):
            return Expression(
                kind="operator",
                operator=_OPERATORS.get(type(node), type(node).__name__),
                operands=[self.expression(node.right)],
                lineno=lineno,
            )
        if _is(node, "Operator"):
            return Expression(
                kind="operator",
                operator=_OPERATORS.get(type(node), type(node).__name__),
                operands=[self.expression(node.left), self.expression(node.right)],
                lineno=lineno,
            )
        return Expression(
            kind="unknown", unknown=True, node_type=type(node).__name__, lineno=lineno
        )

    def _select(self, node: Any, lineno: int | None, mode: str) -> Expression:
        """Bit select, part select or indexed part select (``a[i+:4]``).

        A select on a plain signal is folded into that signal's expression. A
        select on anything else (``mem[i][j]``, ``(a+b)[0]``) keeps its base as
        a separate ``select`` node so inner indices are not overwritten.
        """
        base = self.expression(node.var)
        index = msb = lsb = None
        if mode == "index":
            index = self.expression(node.ptr)
        else:
            msb = self.expression(node.msb)
            lsb = self.expression(node.lsb)
        part_select = {"plus": "+:", "minus": "-:"}.get(mode)

        is_plain_signal = (
            base is not None
            and base.kind == "signal"
            and base.index is None
            and base.msb is None
            and base.lsb is None
        )
        if is_plain_signal:
            base.index, base.msb, base.lsb = index, msb, lsb
            base.part_select = part_select
            return base
        return Expression(
            kind="select",
            base=base,
            index=index,
            msb=msb,
            lsb=lsb,
            part_select=part_select,
            lineno=lineno,
        )

    # ------------------------------------------------------------------ widths

    def _width_of(self, width: vast.Width | None) -> tuple[int | None, BitRange | None]:
        """Width and range of an explicit ``[msb:lsb]``; ``(None, None)`` if absent."""
        if width is None:
            return None, None
        msb_val = self._const_int(width.msb)
        lsb_val = self._const_int(width.lsb)
        bit_range = BitRange(
            msb=msb_val,
            lsb=lsb_val,
            msb_expr=self.expression(width.msb) if msb_val is None else None,
            lsb_expr=self.expression(width.lsb) if lsb_val is None else None,
        )
        if msb_val is not None and lsb_val is not None:
            return abs(msb_val - lsb_val) + 1, bit_range
        return None, bit_range

    def _const_int(self, node: vast.Node | None) -> int | None:
        node = self._unwrap(node)
        if node is None:
            return None
        if _is(node, "Uminus"):
            value = self._const_int(node.right)
            return None if value is None else -value
        if _is(node, "Uplus"):
            return self._const_int(node.right)
        if _is(node, "IntConst"):
            return _parse_verilog_int(str(node.value))
        return None

    @staticmethod
    def _unwrap(node: vast.Node | None) -> vast.Node | None:
        while _is(node, "Lvalue", "Rvalue"):
            node = node.var
        return node

    @staticmethod
    def _name_of(node: Any) -> str | None:
        if node is None:
            return None
        if isinstance(node, str):
            return node
        if isinstance(node, vast.Identifier):
            return node.name
        return str(node)

    # ------------------------------------------------------- clock / reset

    def _infer_clock_reset(self, module: Module) -> dict[str, Any]:
        """Heuristic clock/reset detection. Everything here is marked ``inferred``."""
        clocks: list[InferredClockReset] = []
        resets: list[InferredClockReset] = []
        seen: set[tuple[str, str]] = set()

        def add(item: InferredClockReset) -> None:
            key = (item.role, item.name)
            if key in seen:
                return
            seen.add(key)
            (clocks if item.role == "clock" else resets).append(item)

        for block in module.always_blocks:
            for sens in block.sensitivity:
                if not sens.signal:
                    continue
                if sens.edge in {"posedge", "negedge"}:
                    if is_clock_name(sens.signal):
                        add(
                            InferredClockReset(
                                name=sens.signal,
                                role="clock",
                                reason="edge-triggered sensitivity list",
                                edge=sens.edge,
                            )
                        )
                    if is_reset_name(sens.signal):
                        add(
                            InferredClockReset(
                                name=sens.signal,
                                role="reset",
                                reason="asynchronous edge in sensitivity list",
                                edge=sens.edge,
                            )
                        )
                elif sens.edge in {"level", "all"} and is_reset_name(sens.signal):
                    add(
                        InferredClockReset(
                            name=sens.signal,
                            role="reset",
                            reason="level-sensitive reset in sensitivity list",
                            edge=sens.edge,
                        )
                    )

        for port in module.ports:
            if is_clock_name(port.name):
                add(
                    InferredClockReset(
                        name=port.name,
                        role="clock",
                        reason="port name matches a conventional clock identifier",
                    )
                )
            if is_reset_name(port.name):
                add(
                    InferredClockReset(
                        name=port.name,
                        role="reset",
                        reason="port name matches a conventional reset identifier",
                    )
                )

        return {
            "clock_signals": [item.to_dict() for item in clocks],
            "reset_signals": [item.to_dict() for item in resets],
        }


def _parse_verilog_int(text: str) -> int | None:
    raw = text.replace("_", "").strip()
    if _INT_RE.match(raw):
        return int(raw)
    match = _BASED_INT_RE.match(raw)
    if not match:
        return None
    base_letter, digits = match.group(1).lower(), match.group(2).lower()
    if any(ch in digits for ch in "xz"):
        return None
    base = {"b": 2, "o": 8, "d": 10, "h": 16}[base_letter]
    try:
        return int(digits, base)
    except ValueError:
        return None
