#!/usr/bin/env python3
from __future__ import annotations

import ast
import re
import sys
import textwrap
from pathlib import Path

PYQT_HINTS = {
    "PyQt5",
    "PyQt6",
    "QtWidgets",
    "QtCore",
    "QtGui",
    "QApplication",
    "QWidget",
    "QMainWindow",
    "QDialog",
    "QPainter",
    "QPixmap",
    "QIcon",
}
UI_NAME_RX = re.compile(r"(ui|window|dialog|faceplate|widget|view)", re.I)


def uses_ui(tree: ast.AST, src: str, name: str) -> bool:
    if UI_NAME_RX.search(name):
        return True
    if any(h in src for h in PYQT_HINTS):
        return True
    # se o corpo referencia Q* ou Qt*
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and re.match(r"Q[A-Z]\w*", n.id):
            return True
        if (
            isinstance(n, ast.Attribute)
            and isinstance(n.value, ast.Name)
            and n.value.id in {"QtWidgets", "QtCore", "QtGui"}
        ):
            return True
    return False


def split_file(path: Path, dest_core: Path, dest_ui: Path):
    src = path.read_text(encoding="utf-8", errors="ignore")
    try:
        mod = ast.parse(src)
    except SyntaxError:
        print(f"[SKIP] {path}: sem parse")
        return

    core_defs = []
    ui_defs = []
    other_nodes = []  # imports, consts etc.
    for n in mod.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = n.name
            body_src = ast.get_source_segment(src, n) or ""
            tree = ast.parse(body_src)
            (ui_defs if uses_ui(tree, body_src, name) else core_defs).append(body_src)
        else:
            # manter imports/consts nos dois lados (simplifica)
            other_nodes.append(ast.get_source_segment(src, n) or "")

    core_text = "\n".join(other_nodes + core_defs).strip()
    ui_text = "\n".join(other_nodes + ui_defs).strip()

    stem = path.stem
    out_core = dest_core / f"{stem}_core_extracted.py"
    out_ui = dest_ui / f"{stem}_ui_extracted.py"
    dest_core.mkdir(parents=True, exist_ok=True)
    dest_ui.mkdir(parents=True, exist_ok=True)
    if core_text:
        out_core.write_text(core_text + "\n", encoding="utf-8")
    if ui_text:
        out_ui.write_text(ui_text + "\n", encoding="utf-8")

    # shim que reexporta
    exports = []
    for block in core_defs + ui_defs:
        try:
            t = ast.parse(block)
            for n in t.body:
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    exports.append(n.name)
        except Exception:
            pass
    shim = textwrap.dedent(
        f"""
        # Arquivo dividido automaticamente. Mantido como shim de compat.
        try:
            from simulator.core.{out_core.stem} import *
        except Exception:
            pass
        try:
            from simulator.ui.{out_ui.stem} import *
        except Exception:
            pass
        __all__ = {exports!r}
    """
    ).lstrip()
    path.write_text(shim, encoding="utf-8")
    print(f"[OK] {path} -> {out_core.name} / {out_ui.name} (shim criado)")


def main():
    if len(sys.argv) < 4:
        print("Uso: split_mixed_module.py <arquivo.py> <dest_core_dir> <dest_ui_dir>")
        sys.exit(2)
    src = Path(sys.argv[1])
    dcore = Path(sys.argv[2])
    dui = Path(sys.argv[3])
    split_file(src, dcore, dui)


if __name__ == "__main__":
    main()
