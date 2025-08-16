#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

PAT = re.compile(r"^(\s*)except\s*:\s*(#.*)?$", re.MULTILINE)


def fix_file(p: Path) -> int:
    text = p.read_text(encoding="utf-8", errors="ignore")

    def repl(m):
        indent = m.group(1) or ""
        comment = m.group(2) or ""
        return f"{indent}except Exception as e:{comment}"

    new = PAT.sub(repl, text)
    if new != text:
        p.write_text(new, encoding="utf-8")
        return 1
    return 0


def main(paths: list[str]) -> int:
    changed = 0
    for root in paths:
        rp = Path(root)
        if rp.is_file() and rp.suffix == ".py":
            changed += fix_file(rp)
        else:
            for f in rp.rglob("*.py"):
                changed += fix_file(f)
    print(f"[fix-bare-except] arquivos alterados: {changed}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("uso: python tools/fix_bare_except.py <paths...>")
        sys.exit(2)
    sys.exit(main(sys.argv[1:]))
