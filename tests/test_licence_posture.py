"""The registry must not reproduce verbatim text from the papers it cites.

The project's stated position: numbers, PMCIDs, table labels and licence codes are
published because facts are not copyrightable; verbatim caption and table text from
NC-ND or TDM articles is not. Curating 16 agents from the primary literature put quoted
sentences from 18 papers into a checked-in file, and **14 of those papers are CC BY-NC-ND
or CC BY-NC** -- a licence breach in a published artefact, which is worse than a wrong
number because no later correction undoes the distribution.

The rule enforced here is stricter than the stated one, deliberately. "Quote CC BY freely,
never quote NC-ND" requires whoever edits this hand-maintained file next to look up a
licence first, and a rule that depends on remembering an exception is a rule that breaks.
No quotation from any cited paper is a bright line, and it costs nothing: the design facts
are facts and survive paraphrase, while the citation stays so the claim is still checkable.

The fetch manifests carry `license_code` per PMCID, so the licence mix is measured rather
than assumed: of 1,471 fetched articles, 663 are CC BY, 526 CC BY-NC-ND, 251 CC BY-NC,
12 CC BY-NC-SA, 3 TDM, 2 CC BY-ND and 1 CC0.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "conf" / "adc_registry.yaml"
PMC_RAW = pathlib.Path("/data/hyeongchanahn/adctox/raw/pmc")
# Short enough to be a term of art ("cleavable linker") rather than a reproduced sentence.
MAX_QUOTED_CHARS = 24
QUOTED = re.compile(r"[\"“]([^\"”]+)[\"”]")
PROSE_FIELDS = ("curation_note", "dar_note", "fc_note", "notes")


def _agents() -> dict:
    return yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))["agents"]


def test_no_registry_entry_quotes_a_sentence() -> None:
    offenders = [
        f"{agent}.{field}: {m.group(1)[:60]!r}"
        for agent, spec in _agents().items()
        for field in PROSE_FIELDS
        for m in QUOTED.finditer(str(spec.get(field) or ""))
        if len(m.group(1)) > MAX_QUOTED_CHARS
    ]
    assert not offenders, (
        "paraphrase these and keep the PMCID; the design facts are facts and survive it:\n"
        "  " + "\n  ".join(offenders)
    )


def test_every_curated_agent_still_cites_its_source() -> None:
    """Paraphrasing must not cost the citation. A claim with no PMCID cannot be checked,
    which would trade one failure for another."""
    for agent, spec in _agents().items():
        if not spec.get("curation_source"):
            continue
        blob = " ".join(
            str(spec.get(f) or "") for f in (*PROSE_FIELDS, "curation_source")
        )
        assert re.search(r"PMC\d+|discovery corpus|fda_label|literature", blob), agent


@pytest.mark.skipif(not PMC_RAW.exists(), reason="no PMC snapshot on disk")
def test_the_licence_of_every_cited_article_is_recorded() -> None:
    """A citation whose licence is unknown cannot be checked against any rule. The fetch
    manifests record `license_code` per PMCID precisely so this is answerable."""
    licences: dict[str, str | None] = {}
    for d in sorted(PMC_RAW.glob("*")):
        manifest = d / "_manifest.json"
        if not manifest.exists():
            continue
        for pmcid, rec in json.loads(
            manifest.read_text(encoding="utf-8")
        )["records"].items():
            licences[pmcid] = rec.get("license_code")
    assert licences, "no fetch manifest carries licence codes"

    cited = {
        pmcid
        for spec in _agents().values()
        for field in (*PROSE_FIELDS, "curation_source")
        for pmcid in re.findall(r"PMC(\d+)", str(spec.get(field) or ""))
    }
    assert cited, "no agent cites a PMCID at all"
    unknown = sorted(p for p in cited if p not in licences)
    assert not unknown, (
        "these articles are cited but absent from every fetch manifest, so their licence "
        f"is unverifiable: {unknown[:10]}"
    )


def test_no_finngen_hazard_ratio_is_printed_in_a_published_document() -> None:
    """FinnGen has no named licence, so its numbers stay out of the published documents.

    Checked on 2026-10-10: `finngen.fi/en/access_results` names no licence -- not CC BY,
    not CC0 -- gates the download behind a form, and asks only for citation and
    acknowledgement. No redistribution or derivative terms are stated. That is the same
    situation as `adctoxicityatlas.org` and `ADCdb`, where this project's standing rule is
    cite only, never bulk-collect, never redistribute.

    So the comorbidity layer may *use* the hazard ratios as a capped prior and the report
    may say what the layer changes, but a FinnGen HR must not appear as a figure. The
    workbook itself is already gitignored with only a hash committed, which the atlas
    manifest test covers; this covers the published side.

    The check is deliberately crude -- a document that mentions FinnGen must not put a
    decimal figure in the same sentence -- because the failure it guards against is
    someone transcribing a table of HRs into a results section, and that is exactly what
    a crude check catches.
    """
    import re

    docs = sorted(
        [*(ROOT / "report").rglob("*.md"), *(ROOT / "docs").rglob("*.md")]
    )
    offenders: list[tuple[str, int, str]] = []
    decimal = re.compile(r"(?<![\w.])\d+\.\d{2,}(?!\w)")
    for doc in docs:
        for lineno, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            if "FinnGen" not in line and "finngen" not in line:
                continue
            # A URL carries dots and no hazard ratios.
            stripped = re.sub(r"\S*finngen\.fi\S*", " ", line, flags=re.I)
            stripped = re.sub(r"R\d+", " ", stripped)
            hits = decimal.findall(stripped)
            if hits:
                offenders.append((doc.name, lineno, ", ".join(hits)))
    assert not offenders, (
        "a decimal figure sits in a sentence about FinnGen, which has no named licence and "
        "is cite-only in this project: "
        + "; ".join(f"{d}:{n} ({h})" for d, n, h in offenders)
    )
