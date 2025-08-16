#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

FORBIDDEN = (
    r"^\s*from\s+PyQt(5|6)\.",  # from PyQt5.QtWidgets import ...
    r"^\s*import\s+PyQt(5|6)",  # import PyQt5
    r"\bQ(Application|Widget|MainWindow|Dialog|Painter|Pixmap|Icon)\b",
)
PAT = re.compile("|".join(FORBIDDEN))

ROOTS = [
    "simulator/core",
    "simulator/dsl",
    "simulator/objects",
]


def main():
    bad = []
    for root in ROOTS:
        p = Path(root)
        if not p.exists():
            continue
        for f in p.rglob("*.py"):
            text = f.read_text(encoding="utf-8", errors="ignore")
            for i, line in enumerate(text.splitlines(), 1):
                if PAT.search(line):
                    bad.append(f"{f.as_posix()}:{i}: UI/PyQt no core/dsl/objects")
    if bad:
        print("\n".join(bad))
        print("\n[ERRO] Remova referências de UI/PyQt do core/dsl/objects.")
        sys.exit(1)


if __name__ == "__main__":
    main()
