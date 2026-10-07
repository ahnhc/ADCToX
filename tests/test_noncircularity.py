"""The validation modules must not import the scoring path.

The plan calls this a mechanical guarantee of non-circularity, and it held only by
accident: nothing checked it. The modules under `adctox.validation` extract ground truth
from approved labels -- which organ a dose-modification table fears, which section-5
heading appeared on which date. If one of them could reach the model, the ground truth
could come to depend on the thing being scored, and the dependency would be invisible in
a result that still looked like a held-out comparison.

The *scripts* that run these evaluations necessarily import both sides; they are the
harness. The constraint is on the extraction modules, and it is checked transitively,
because a two-hop import is no less circular for being indirect.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
PKG = "adctox"

# The scoring path: anything that fits, predicts, scores or ranks.
SCORING = {
    "adctox.model",
    "adctox.model.forward",
    "adctox.model.predict",
    "adctox.model.dataset",
    "adctox.model.splits",
    "adctox.design",
    "adctox.design.search",
    "adctox.design.constraints",
    "adctox.design.enumerate",
    "adctox.pipeline",
    "adctox.api",
    "adctox.api.main",
    "adctox.comorbidity.exclusion_prior",
    "adctox.comorbidity.hard_flags",
}


def _module_name(path: Path) -> str:
    rel = path.relative_to(SRC).with_suffix("")
    parts = [p for p in rel.parts if p != "__init__"]
    return ".".join(parts)


def _imports(path: Path) -> set[str]:
    """First-party modules this file imports, including inside functions."""
    out: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8"))
    pkg_parts = _module_name(path).split(".")[:-1]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith(PKG):
                    out.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:                      # relative
                base = pkg_parts[: len(pkg_parts) - node.level + 1]
                mod = ".".join(base + ([node.module] if node.module else []))
                out.add(mod)
                for a in node.names:
                    out.add(f"{mod}.{a.name}")
            elif node.module and node.module.startswith(PKG):
                out.add(node.module)
                for a in node.names:
                    out.add(f"{node.module}.{a.name}")
    return out


def _closure(start: str, graph: dict[str, set[str]]) -> set[str]:
    seen, stack = set(), [start]
    while stack:
        cur = stack.pop()
        for dep in graph.get(cur, set()):
            if dep in seen:
                continue
            seen.add(dep)
            stack.append(dep)
    return seen


@pytest.fixture(scope="module")
def graph() -> dict[str, set[str]]:
    return {_module_name(p): _imports(p) for p in SRC.rglob("*.py")}


def test_validation_modules_do_not_reach_the_scoring_path(graph):
    validation = [m for m in graph if m.startswith("adctox.validation") and m != "adctox.validation"]
    assert validation, "no validation modules found; this test would pass vacuously"
    for mod in validation:
        reach = _closure(mod, graph)
        leaked = sorted(reach & SCORING)
        assert not leaked, (
            f"{mod} reaches the scoring path via {leaked}. The validation modules extract "
            "ground truth from approved labels; if they can reach the model, the ground "
            "truth can depend on what is being scored and the evaluation stops being "
            "held out."
        )


def test_the_check_would_notice_a_direct_import(graph):
    """Guard against the guard passing vacuously, which is this project's recurring bug."""
    fake = dict(graph)
    fake["adctox.validation.probe"] = {"adctox.model.predict"}
    reach = _closure("adctox.validation.probe", fake)
    assert reach & SCORING, "the reachability check cannot see a direct import"


def test_the_check_would_notice_a_two_hop_import(graph):
    fake = dict(graph)
    fake["adctox.validation.probe"] = {"adctox.helper_probe"}
    fake["adctox.helper_probe"] = {"adctox.pipeline"}
    reach = _closure("adctox.validation.probe", fake)
    assert "adctox.pipeline" in reach, "the reachability check is not transitive"
