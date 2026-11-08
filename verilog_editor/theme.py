"""VS Code–inspired dark theme colors for the Verilog editor."""

from dataclasses import dataclass


@dataclass(frozen=True)
class EditorTheme:
    """Color palette matching a VS Code Dark+ style."""

    background: str = "#1e1e1e"
    foreground: str = "#d4d4d4"
    selection: str = "#264f78"
    current_line: str = "#2a2a2a"
    line_number_bg: str = "#1e1e1e"
    line_number_fg: str = "#858585"
    caret: str = "#aeafad"
    margin_fold: str = "#1e1e1e"
    fold_marker: str = "#c5c5c5"
    matched_brace: str = "#0e639c"
    unmatched_brace: str = "#be1100"
    edge: str = "#3c3c3c"
    status_bg: str = "#007acc"
    status_fg: str = "#ffffff"
    tab_bg: str = "#252526"
    tab_selected: str = "#1e1e1e"
    tab_fg: str = "#cccccc"
    menu_bg: str = "#252526"
    menu_fg: str = "#cccccc"
    find_bg: str = "#252526"
    find_border: str = "#3c3c3c"
    find_input_bg: str = "#3c3c3c"
    find_input_fg: str = "#cccccc"
    button_bg: str = "#0e639c"
    button_fg: str = "#ffffff"
    button_hover: str = "#1177bb"

    # Syntax colors (Dark+)
    keyword: str = "#569cd6"
    comment: str = "#6a9955"
    string: str = "#ce9178"
    number: str = "#b5cea8"
    operator: str = "#d4d4d4"
    identifier: str = "#9cdcfe"
    preprocessor: str = "#c586c0"
    system_task: str = "#dcdcaa"


DARK_THEME = EditorTheme()
