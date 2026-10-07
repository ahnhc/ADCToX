#!/usr/bin/env python
"""Unused-import check, for an environment without ruff.

Exists because a first crude version of this reported 43 unused imports, about thirty of
which were `from __future__ import annotations` -- an import whose effect is not a name,
so a name-based check always calls it unused. A check with a 70% false-positive rate is
worse than none: it trains you to skim the output, which is exactly how the report's
number guard went unnoticed while passing 99% of fabricated figures.

So `__future__` is excluded, and names that only appear inside string annotations are too.
What remained was 16 real findings, all removed. Exits non-zero if any reappear.
"""
import ast, pathlib, sys
issues=[]
roots=[pathlib.Path('src'), pathlib.Path('scripts'), pathlib.Path('tests')]
for root in roots:
    for f in sorted(root.rglob('*.py')):
        src=f.read_text(); tree=ast.parse(src)
        imported={}
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                for a in n.names: imported[(a.asname or a.name).split('.')[0]]=n.lineno
            elif isinstance(n, ast.ImportFrom):
                if n.module == '__future__': continue   # effect, not a name
                for a in n.names:
                    if a.name!='*': imported[a.asname or a.name]=n.lineno
        used={n.id for n in ast.walk(tree) if isinstance(n,ast.Name)}
        used|={n.attr for n in ast.walk(tree) if isinstance(n,ast.Attribute)}
        for name,line in sorted(imported.items()):
            if name in used: continue
            # annotations written as strings
            if f'"{name}' in src or f"'{name}" in src: continue
            issues.append(f"{f}:{line} {name}")
for i in issues:
    print("  " + i)
print(f"{len(issues)} unused imports")
sys.exit(1 if issues else 0)
