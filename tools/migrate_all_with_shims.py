#!/usr/bin/env python3
from __future__ import annotations

import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
BUILD.mkdir(parents=True, exist_ok=True)

LEGACY_ROOTS = ["BRICSIM_Simulator", "BRICSSIM_Designer"]
EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "build",
    "dist",
    "tools",
    ".idea",
    ".vscode",
}

PYQT_HINTS = {
    "PyQt5",
    "PyQt6",
    "QtWidgets",
    "QtCore",
    "QtGui",
    "QMainWindow",
    "QWidget",
    "QDialog",
    "QGraphics",
    "QPainter",
}
DSL_HINTS = {
    "lexer",
    "parser",
    "token",
    "grammar",
    "ast",
    "eval",
    "compile",
    "expression",
    "interpreter",
}
OBJ_HINTS = {
    "Pump",
    "Valve",
    "Sensor",
    "Actuator",
    "Tag",
    "Equipment",
    "Vessel",
    "Controller",
    "PID",
}
CORE_HINTS = {
    "simulate",
    "solver",
    "engine",
    "loop",
    "control",
    "controle",
    "pid",
    "model",
    "calc",
    "physics",
    "thermo",
}


@dataclass
class MovePlan:
    src: Path
    dest_pkg: str  # e.g. "simulator/ui"
    reason: str


def guess_dest(src: Path) -> MovePlan:
    text = src.read_text(encoding="utf-8", errors="ignore")
    name = src.stem
    legacy_root = src.parts[0]
    base = "simulator" if legacy_root == "BRICSIM_Simulator" else "design"

    # 1) scripts (entrypoints)
    if "__main__" in text:
        return MovePlan(src, "scripts", "tem if __name__ == '__main__'")

    # 2) UI (PyQt)
    if any(h in text for h in PYQT_HINTS) or re.search(
        r"(ui|window|dialog|form|faceplate)", name, re.I
    ):
        dest = f"{base}/ui"
        return MovePlan(src, dest, "imports/bases PyQt* ou nome sugere UI")

    # 3) DSL (apenas para simulator)
    if base == "simulator" and any(h in text for h in DSL_HINTS):
        return MovePlan(src, "simulator/dsl", "léxico/gramática/AST")

    # 4) Objetos de domínio (apenas para simulator)
    if base == "simulator" and (
        any(k in text for k in OBJ_HINTS)
        or re.search(
            r"(pump|valve|sensor|actuator|vessel|equip|object|tag)", name, re.I
        )
    ):
        return MovePlan(src, "simulator/objects", "vocabulário/classes de domínio")

    # 5) Core
    if any(h in text for h in CORE_HINTS) or re.search(
        r"(core|engine|sim|control|pid|solver|model)", name, re.I
    ):
        return MovePlan(
            src,
            f"{base}/core" if base == "simulator" else "design/ui",
            "engine/controle/modelo",
        )

    # 6) Fallbacks
    if base == "simulator":
        return MovePlan(src, "simulator/core", "fallback conservador (simulator/core)")
    return MovePlan(src, "design/ui", "fallback conservador (design/ui)")


def dotted(path_like: str) -> str:
    return path_like.replace("\\", "/").strip("/").replace("/", ".")


def write_shim(old_path: Path, dest_module: str):
    shim = f'''"""
Shim de compatibilidade: módulo movido para {dest_module}.
Este arquivo será depreciado em versões futuras.
"""
from warnings import warn as _warn
_warn("Módulo movido para {dest_module}", DeprecationWarning, stacklevel=2)
from {dest_module} import *  # noqa: F401,F403
'''
    old_path.parent.mkdir(parents=True, exist_ok=True)
    old_path.write_text(shim, encoding="utf-8")


def iter_candidates():
    for legacy in LEGACY_ROOTS:
        base = ROOT / legacy
        if not base.exists():
            continue
        for p in base.rglob("*.py"):
            if p.name == "__init__.py":
                # manter __init__ no lugar para não bagunçar pacotes legados
                continue
            if any(part in EXCLUDE_DIRS for part in p.parts):
                continue
            yield p


def main():
    apply = "--apply" in sys.argv
    moves: list[MovePlan] = []
    for src in iter_candidates():
        mp = guess_dest(src)
        moves.append(mp)

    # relatório
    out = [
        "# Migração BRICSim – Plano gerado",
        "",
        "| Arquivo | Destino | Razão |",
        "|---|---|---|",
    ]
    for m in moves:
        rel = m.src.relative_to(ROOT).as_posix()
        out.append(f"| `{rel}` | `{m.dest_pkg}` | {m.reason} |")
    (BUILD / "migrate_report.md").write_text("\n".join(out), encoding="utf-8")

    if not apply:
        print(
            "[DRY-RUN] Plano escrito em build/migrate_report.md. Rode com --apply para executar."
        )
        return

    # aplicar
    moved, skipped = 0, 0
    for m in moves:
        src = m.src
        dest_dir = ROOT / m.dest_pkg
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        if dest.exists():
            print(f"[SKIP] destino já existe: {dest.relative_to(ROOT)}")
            skipped += 1
            continue
        # mover
        shutil.move(str(src), str(dest))
        # criar shim no lugar antigo
        dest_module = dotted(f"{m.dest_pkg}/{src.stem}")
        write_shim(src, dest_module)
        print(f"[OK] {src.relative_to(ROOT)} -> {dest.relative_to(ROOT)} (shim criado)")
        moved += 1

    print(f"[DONE] Movidos: {moved} | Skippados: {skipped}")
    print("Relatório: build/migrate_report.md")


if __name__ == "__main__":
    main()
