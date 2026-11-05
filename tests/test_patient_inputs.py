"""What a typed or picked patient input turns into: the registry condition behind it, the lab value it means, the verdict it gets."""
import pathlib, sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))
import form
import recommend as RC


def row_of(rows, adc): return next(r for r in rows if r["adc"] == adc)


@pytest.mark.parametrize("typed", ["bleomycin", "Bleomycin", "블레오마이신", "concomitant bleomycin", "Concomitant  Bleomycin", "concomitant_bleomycin"])
def test_typed_bleomycin_contraindicates_brentuximab(typed):
    rows, _, notes, _ = RC.recommend([typed])
    row = row_of(rows, "brentuximab-vedotin")
    assert row["verdict"].worst_known == RC.RS.TIER["contraindicated"] and row["restriction"].startswith("Contraindicated")
    assert notes == [(typed, RC.CONTEXT["concomitant_bleomycin"])] and RC.unresolved([typed]) == []
    assert RC.analyze_conditions([typed]) == [] and RC.ambiguous_conditions([typed]) == []


def test_the_bleomycin_suggestion_reads_back_as_the_rule_condition():
    import suggest as SG
    for typed in ("bleomycin", "블레오마이신"):
        kind, value, label, *_ = SG.names(RC, typed)[0]
        assert kind == "text" and "bleomycin" in label.lower()
        _, free, _ = form.Form._split(None, [(kind, value, label, "", [])])
        assert RC.resolve(form.split_free(free))[2] == {"concomitant_bleomycin"}
