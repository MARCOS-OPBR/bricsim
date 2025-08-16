#!/usr/bin/env python3
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESTS = {"core", "ui", "dsl", "objects", "scripts", "design", "simulator"}


def main():
    if len(sys.argv) != 3 or sys.argv[2] not in DESTS:
        print(
            "Uso: safe_move_with_shim.py <arquivo.py> <core|ui|dsl|objects|scripts|design|simulator>"
        )
        sys.exit(2)
    src = (ROOT / sys.argv[1]).resolve()
    dest_pkg = sys.argv[2]
    if not src.exists() or src.suffix != ".py":
        print("Arquivo inválido.")
        sys.exit(2)

    rel = src.relative_to(ROOT)
    target = ROOT / dest_pkg / rel.name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(target))

    shim = f'''"""
Shim de compatibilidade: reexporta de {dest_pkg}.
"""
from warnings import warn
warn("Módulo movido para {dest_pkg}/{rel.name}", DeprecationWarning, stacklevel=2)
from {dest_pkg}.{rel.stem} import *  # noqa: F401,F403
'''
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(shim, encoding="utf-8")
    print(f"[OK] movido: {rel} -> {dest_pkg}/{rel.name}")
    print(f"[OK] shim em: {rel}")


if __name__ == "__main__":
    main()
