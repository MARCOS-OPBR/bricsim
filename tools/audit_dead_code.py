#!/usr/bin/env python3
"""
BRICSim – Auditor de módulos órfãos e definições suspeitas (funções/classes não referenciadas).

Conservador e só-ler:
- Monta grafo de imports intra-repo (pastas passadas em --roots).
- Aponta "módulos órfãos" (sem imports inbound, não-entrypoint, não-testes).
- Aponta funções/classes top-level não usadas internamente/externamente e fora de __all__.
- NÃO toca em nada; gera build/audit_report.json e .md

Uso típico (monorepo design/simulator):
  python tools/audit_dead_code.py --roots simulator/core simulator/dsl simulator/tools simulator/scripts tests --json-out build/audit_simulator.json --md-out build/audit_simulator.md
  python tools/audit_dead_code.py --roots design tools scripts tests --json-out build/audit_design.json --md-out build/audit_design.md
"""
from __future__ import annotations

import argparse
import ast
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
PY_EXT = ".py"

DEFAULT_ROOTS = ["core", "dsl", "tools", "scripts", "tests"]
EXCLUDE_DIRS = {
    "ui",
    "objects",
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "build",
    "dist",
    "__pycache__",
    ".idea",
    ".vscode",
    ".eggs",
    ".tox",
}


class ModuleInfo:
    def __init__(self, path: Path, module: str):
        self.path = path
        self.module = module
        self.tree: Optional[ast.AST] = None
        self.imports: Set[str] = set()
        self.raw_imports: Set[str] = set()
        self.entrypoint = False
        self.is_test = self._guess_is_test()
        self.def_funcs: Set[str] = set()
        self.def_classes: Set[str] = set()
        self.dunder_all: Set[str] = set()
        self.from_import_alias: Dict[str, Tuple[str, str]] = {}
        self.module_alias: Dict[str, str] = {}
        self.local_uses: Set[str] = set()

    def _guess_is_test(self) -> bool:
        p = self.path.as_posix()
        name = self.path.name
        return "tests/" in p or name.startswith("test_") or name.endswith("_test.py")


def path_to_module(root: Path, file_path: Path) -> str:
    rel = file_path.relative_to(root).with_suffix("")
    return ".".join(rel.parts)


def discover_python_files(roots: List[str]) -> List[Path]:
    files: List[Path] = []
    for r in roots:
        base = REPO_ROOT / r
        if not base.exists():
            continue
        for path in base.rglob(f"*{PY_EXT}"):
            if any(part in EXCLUDE_DIRS for part in path.parts):
                continue
            files.append(path)
    return files


def parse_module(file_path: Path) -> Optional[ast.AST]:
    try:
        text = file_path.read_text(encoding="utf-8")
        return ast.parse(text, filename=str(file_path))
    except Exception:
        return None


def has_dunder_main(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and isinstance(
            getattr(node, "test", None), ast.Compare
        ):
            left = node.test.left
            if isinstance(left, ast.Name) and left.id == "__name__":
                for comp in node.test.comparators:
                    if isinstance(comp, ast.Constant) and comp.value == "__main__":
                        return True
    return False


def collect_dunder_all(tree: ast.AST) -> Set[str]:
    exported = set()
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    if isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(
                                elt.value, str
                            ):
                                exported.add(elt.value)
    return exported


def resolve_relative(base_module: str, level: int, name: Optional[str]) -> str:
    if level == 0:
        return name or ""
    base_parts = base_module.split(".")
    if level > len(base_parts):
        return name or ""
    prefix = ".".join(base_parts[:-level])
    return f"{prefix}.{name}" if name else prefix


def analyze_module(mi, known_modules: Set[str]):
    tree = parse_module(mi.path)
    mi.tree = tree
    if tree is None:
        return
    mi.entrypoint = has_dunder_main(tree)
    mi.dunder_all = collect_dunder_all(tree)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                raw = alias.name
                mi.raw_imports.add(raw)
                asname = alias.asname or raw.split(".")[-1]
                mi.module_alias[asname] = raw
                if raw in known_modules:
                    mi.imports.add(raw)
        elif isinstance(node, ast.ImportFrom):
            modname = resolve_relative(
                mi.module, getattr(node, "level", 0), node.module
            )
            raw_base = modname or ""
            for alias in node.names:
                raw = f"{raw_base}.{alias.name}" if raw_base else alias.name
                mi.raw_imports.add(raw_base or raw)
                if raw_base in known_modules:
                    mi.imports.add(raw_base)
                asname = alias.asname or alias.name
                if raw_base:
                    mi.from_import_alias[asname] = (raw_base, alias.name)

    for node in getattr(tree, "body", []):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            mi.def_funcs.add(node.name)
        elif isinstance(node, ast.ClassDef):
            mi.def_classes.add(node.name)

    local_defs = mi.def_funcs | mi.def_classes
    used_imported_symbols: Set[Tuple[str, str]] = set()

    class UseVisitor(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call):
            if isinstance(node.func, ast.Name):
                n = node.func.id
                if n in local_defs:
                    mi.local_uses.add(n)
                if n in mi.from_import_alias:
                    used_imported_symbols.add(mi.from_import_alias[n])
            elif isinstance(node.func, ast.Attribute) and isinstance(
                node.func.value, ast.Name
            ):
                base = node.func.value.id
                attr = node.func.attr
                if base in mi.module_alias:
                    used_imported_symbols.add((mi.module_alias[base], attr))
            self.generic_visit(node)

        def visit_Name(self, node: ast.Name):
            if isinstance(node.ctx, ast.Load) and node.id in mi.from_import_alias:
                used_imported_symbols.add(mi.from_import_alias[node.id])

        def visit_ClassDef(self, node: ast.ClassDef):
            for b in node.bases:
                if isinstance(b, ast.Name) and b.id in mi.from_import_alias:
                    used_imported_symbols.add(mi.from_import_alias[b.id])
            self.generic_visit(node)

        def visit_AnnAssign(self, node: ast.AnnAssign):
            t = node.annotation
            if isinstance(t, ast.Name) and t.id in mi.from_import_alias:
                used_imported_symbols.add(mi.from_import_alias[t.id])
            self.generic_visit(node)

    UseVisitor().visit(tree)
    return used_imported_symbols


def main():
    ap = argparse.ArgumentParser(
        description="Auditor BRICSim – órfãos e defs suspeitas"
    )
    ap.add_argument(
        "--roots", nargs="*", default=DEFAULT_ROOTS, help="Pastas raiz a varrer"
    )
    ap.add_argument(
        "--json-out", default=str(REPO_ROOT / "build" / "audit_report.json")
    )
    ap.add_argument("--md-out", default=str(REPO_ROOT / "build" / "audit_report.md"))
    args = ap.parse_args()

    files = [p for p in discover_python_files(args.roots) if p.suffix == PY_EXT]

    known_modules: Dict[str, ModuleInfo] = {}
    for fp in files:
        module = path_to_module(REPO_ROOT, fp)
        known_modules[module] = ModuleInfo(fp, module)

    used_imported_symbols_global: Set[Tuple[str, str]] = set()
    for module, mi in known_modules.items():
        used_here = analyze_module(mi, set(known_modules.keys()))
        if isinstance(used_here, set):
            used_imported_symbols_global |= used_here

    inbound_count: Dict[str, int] = defaultdict(int)
    for module, mi in known_modules.items():
        for dep in mi.imports:
            if dep in known_modules and dep != module:
                inbound_count[dep] += 1

    orphan_modules = []
    for module, mi in known_modules.items():
        if mi.is_test:
            continue
        name = Path(mi.path.name).stem.lower()
        if name in {"main", "cli", "__init__"}:
            continue
        if mi.entrypoint:
            continue
        if inbound_count.get(module, 0) == 0:
            orphan_modules.append(
                {
                    "module": module,
                    "path": str(mi.path.relative_to(REPO_ROOT)),
                    "reason": "Sem imports internos (inbound=0) e não é entrypoint/test.",
                }
            )

    suspect_defs = []
    for module, mi in known_modules.items():
        for fn in sorted(mi.def_funcs):
            used_internally = fn in mi.local_uses
            used_externally = (module, fn) in used_imported_symbols_global
            exported = fn in mi.dunder_all
            if not (used_internally or used_externally or exported):
                severity = "low" if fn.startswith("_") else "normal"
                suspect_defs.append(
                    {
                        "module": module,
                        "path": str(mi.path.relative_to(REPO_ROOT)),
                        "def": fn,
                        "kind": "function",
                        "severity": severity,
                        "reason": "Sem uso interno, sem import externo e fora de __all__.",
                    }
                )
        for cl in sorted(mi.def_classes):
            used_internally = cl in mi.local_uses
            used_externally = (module, cl) in used_imported_symbols_global
            exported = cl in mi.dunder_all
            if not (used_internally or used_externally or exported):
                severity = "low" if cl.startswith("_") else "normal"
                suspect_defs.append(
                    {
                        "module": module,
                        "path": str(mi.path.relative_to(REPO_ROOT)),
                        "def": cl,
                        "kind": "class",
                        "severity": severity,
                        "reason": "Sem instanciação interna, sem import externo e fora de __all__.",
                    }
                )

    unresolved_imports = []
    known_set = set(known_modules.keys())
    for module, mi in known_modules.items():
        for raw in sorted(mi.raw_imports):
            seems_internal = any(
                raw.startswith(f"{r}.") or raw == r
                for r in ["design", "simulator"] + DEFAULT_ROOTS
            )
            if seems_internal and raw not in known_set:
                unresolved_imports.append(
                    {
                        "module": module,
                        "path": str(mi.path.relative_to(REPO_ROOT)),
                        "import": raw,
                        "reason": "Import intra-repo não resolvido (verifique caminho/namespace).",
                    }
                )

    out_dir = Path(args.json_out).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": {
            "total_modules": len(known_modules),
            "orphan_modules": len(orphan_modules),
            "suspect_defs": len(suspect_defs),
            "unresolved_imports": len(unresolved_imports),
        },
        "orphan_modules": orphan_modules,
        "suspect_defs": suspect_defs,
        "unresolved_imports": unresolved_imports,
    }
    (REPO_ROOT / args.json_out).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    md_lines = []
    md_lines += ["# BRICSim – Relatório de Auditoria", "", "## Resumo"]
    md_lines += [
        f"- Módulos varridos: **{len(known_modules)}**",
        f"- Candidatos a órfãos: **{len(orphan_modules)}**",
        f"- Definições suspeitas: **{len(suspect_defs)}**",
        f"- Imports intra-repo não resolvidos: **{len(unresolved_imports)}**",
        "",
    ]
    md_lines.append("## Módulos órfãos (candidatos)")
    if orphan_modules:
        md_lines += ["| Módulo | Caminho | Razão |", "|---|---|---|"]
        for it in orphan_modules:
            md_lines.append(f"| `{it['module']}` | `{it['path']}` | {it['reason']} |")
    else:
        md_lines.append("_Nenhum candidato._")
    md_lines.append("")
    md_lines.append("## Definições suspeitas (funções/classes)")
    if suspect_defs:
        md_lines += [
            "| Módulo | Caminho | Def | Tipo | Severidade | Razão |",
            "|---|---|---|---|---|---|",
        ]
        for it in suspect_defs:
            md_lines.append(
                f"| `{it['module']}` | `{it['path']}` | `{it['def']}` | {it['kind']} | {it['severity']} | {it['reason']} |"
            )
    else:
        md_lines.append("_Nenhuma candidata._")
    md_lines.append("")
    md_lines.append("## Imports intra-repo não resolvidos (para revisão)")
    if unresolved_imports:
        md_lines += ["| Módulo | Caminho | Import | Razão |", "|---|---|---|---|"]
        for it in unresolved_imports:
            md_lines.append(
                f"| `{it['module']}` | `{it['path']}` | `{it['import']}` | {it['reason']} |"
            )
    else:
        md_lines.append("_Nenhum apontamento._")
    md_lines.append("")
    Path(args.md_out).write_text("\n".join(md_lines), encoding="utf-8")

    print(f"[OK] Relatórios gerados:\n - {args.json_out}\n - {args.md_out}")


if __name__ == "__main__":
    main()
