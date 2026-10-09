"""Fold extracted paper cells into the corpus schema the model already reads.

The model matrix is built from two frames -- arms and observations -- and the literature
path has to produce the same columns or it is not an extension, it is a second pipeline.
So this writes `paper_arms.parquet` and `paper_observations.parquet` in the registry's
schema, and `make corpus` unions them.

Four decisions, each of which could silently corrupt the fit.

**An arm is a column, not a paper.** A table with a 1.8 mg/kg column and a 2.4 mg/kg
column is two arms of one trial, which is what makes the trial random effect do its job.
Pooling them into a paper-level arm would average two dose levels and attribute the result
to neither.

**The trial id is the join to the registry, not a label.** An arm carrying NCT03589469
shares its trial intercept with the registry's arms from the same trial, which is correct:
they are the same patients. Papers with no resolved trial get the single-arm sentinel,
since a made-up trial id would invent an independent trial.

**The threshold is written as an upper bound and flagged as one.** The dataset builder
treats `frequency_threshold` as the exact cut and censors every unreported axis below
`ceil(n * thresh / 100)`. For the 70% of tables whose cut was derived rather than stated,
that cut is too large, so more mass is treated as possibly-hidden than really was -- the
intervals widen and nothing is claimed that the data does not support. But the flag has to
travel, because the sensitivity analysis that matters is a refit on the explicit-threshold
tables alone.

**A paper's serious-event table is not its common-event table.** The two rank organs
differently -- measured mean rho +0.1455 on the registry corpus -- and the model fits them
separately, with `serious` treated as complete reporting. So the caption decides which
table a set of cells belongs to, and a table that cannot be classified goes to `other`,
where censoring applies and a wrong guess costs width rather than correctness.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys

import pandas as pd
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from adctox.extract.table_to_cells import AGENT_CLASS_HEADER  # noqa: E402
from adctox.provenance import stamp  # noqa: E402
from adctox.taxonomy import default_taxonomy  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "conf" / "adc_registry.yaml"

# A caption naming serious events as the table's subject, not a row inside it.
SERIOUS_TABLE = re.compile(
    r"^\s*(?:table\s*\S{0,4}\.?\s*)?(?:summary\s+of\s+)?"
    r"(?:treatment[-\s]\w+\s+)?serious\s+(?:adverse\s+events?|teaes?|aes?)",
    re.I,
)
# Design columns the dataset builder reads off an arm. Sourced from the registry, so a
# paper arm and a registry arm of the same agent carry identical design features -- which
# is the whole reason design features are agent-level constants in this corpus.
DESIGN_COLS = (
    "mechanism", "payload_family", "payload", "linker_type", "linker_cleavable",
    "dar", "isotype", "target", "conventional_adc",
)


# What outcome does a column actually report? `otherEvents` on ClinicalTrials.gov is
# any-grade, all-cause incidence, and a paper column is only comparable to it if it reports
# the same thing. Several do not, and they were all being merged in as though they did:
#
#   grade_restricted   100 arms  "Grade >=3", "Grade 3-4" -- the severe tail, five to ten
#                                times lower. The clearest case was a trastuzumab
#                                deruxtecan arm reporting nausea at 1.4% against a median
#                                of 67% across its other 79 arms.
#   fatal                3 arms  "Grade 5" -- deaths per organ, near zero everywhere.
#   serious              1 arm   a serious-event column, which belongs to the other table.
#   dose_modification    2 arms  "EV Dose Reduction", "Permanent Discontinuation" -- a
#                                clinical action per organ, not an incidence at all.
#
# 106 of 414 literature arms. Setting them aside costs no agents: every agent with one also
# has an any-grade arm. No registry arm is affected, because a ClinicalTrials.gov event
# group has no outcome qualifier in its title.
#
# Classified rather than dropped here, so the counts are reportable and the arms stay
# available to a severity-stratified outcome later. `dataset.build` keeps them out of the
# any-grade grid.
# What the column reports, which `otherEvents` on ClinicalTrials.gov answers as any-grade,
# all-cause incidence. The first version of this classifier caught only the severe tail and
# had two pattern bugs that a sweep of all 516 column headers exposed:
#
#   * "Grades 3-4" -- the plural. `grade\s*` cannot cross the "s".
#   * "Grade 3n (%)" -- `3\b` fails before a letter.
#
# and it missed the low grades entirely. A column headed "Grade 1-2" is no more any-grade
# than one headed "Grade >=3", and 42 arms carried one: Grade 1, Grade 2, Grade 1-2,
# Grade 4, Grade I-II, Grade III-IV. The pattern now matches any grade number, Arabic or
# Roman, and defers to an explicit all-grade or any-grade claim in the same header, which is
# how a spanning header split upstream reads.
def _header_key(header: str) -> str:
    """A readable but unique fragment of a column header.

    The key was the first 40 characters, and a grade suffix often sits past them:
    "Belamaf 2.5 mg/kg, N = 95: No. of Patients (%) Any Grade" and the same header ending
    "Grade >=3" are identical for 46 characters. 12 keys collapsed 28 distinct columns and
    337 cells, 5.3% of the corpus.

    While both halves were `kind="other"` the groupby merged them into one arm and the
    per-axis maximum took the any-grade value, so the rate survived and the arm carried a
    mixture. Splitting the severe tail into its own table turned that into two rows sharing
    one key, which breaks the frame: `build` indexes arms positionally and looks observations
    up by key, so the grade-restricted row would find the any-grade row's observations and
    enter the grid on a fallback denominator.

    So the prefix stays for legibility and a digest of the whole header is appended whenever
    it was truncated. Keys change, which is why the corpus has to be rebuilt and anything
    fitted on the old keys refitted.
    """
    text = str(header or "")
    if len(text) <= 40:
        return text
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:6]
    return f"{text[:40]}#{digest}"


ANY_GRADE = re.compile(r"all[-\s]*grades?|any[-\s]*grades?|maximum\s+grade", re.I)
# Grade 3 and above, Arabic or Roman, including the open forms "Grade >=3" and "Grade 3-".
# This is the half of the grade-restricted set that becomes its own outcome table.
SEVERE_TAIL = re.compile(
    r"grades?\s*(?:[>=\u2265]\s*)?(?:[345]|III|IV|V)\b"
    r"|grades?\s*3\s*[-\u2013/]",
    re.I,
)
GRADE_NUMBER = re.compile(
    r"grades?\s*[>=\u2265\u2264<]*\s*(?:[1-5](?![0-9])|I{1,3}V?\b)", re.I
)
# A clinical action per organ -- hospitalisation, a hold, a dose reduction, steroid use --
# which is not an incidence at all. Named for the category rather than for one member of it:
# "Hospitalization" is not a dose modification.
ACTION = re.compile(
    r"hospitali|\bhold\b|\bdelay\b|corticosteroid|premedication|dose\s*reduc"
    r"|discontinu|withdraw|interrupt|dose\s*modif",
    re.I,
)
# A cross-tab stub or the table's label column, not a data column. Narrow on purpose:
# "No primary prophylaxis group (n = 203)" is an arm and "Total (N = 66)" is a pooled total.
STUB = re.compile(r"^(?:yes|no)\s*[,:]|^adverse\s+events?$", re.I)
OUTCOME_PATTERNS = (
    # Order matters, and the first match names the column.
    ("not_an_arm", STUB),
    ("clinical_action", ACTION),
    ("fatal", re.compile(r"grades?\s*5\b|\bfatal\b|\bdeaths?\b", re.I)),
    ("serious", re.compile(r"\bserious\b|\bSAE\b", re.I)),
    ("grade_restricted", GRADE_NUMBER),
)


def column_outcome(header: str) -> str:
    """Which outcome the column reports; `any_grade` is the one the corpus wants."""
    text = str(header or "").strip()
    for name, pattern in OUTCOME_PATTERNS:
        if name == "not_an_arm":
            if pattern.match(text):
                return name
            continue
        if pattern.search(text):
            if name == "grade_restricted" and ANY_GRADE.search(text):
                continue
            return name
    return "any_grade"


def names_an_agent_class(header: str) -> bool:
    """True where the column pools a class of agents rather than naming one.

    The predicate lives in `adctox.extract.table_to_cells`, which is where the attribution
    decision belongs and where it now runs for any future extraction. It is applied again
    here because the cells already on disk were extracted before it existed, and
    re-extracting 1,471 articles to drop eleven cells is the wrong trade.
    """
    return bool(AGENT_CLASS_HEADER.search(str(header or "")))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cells", type=pathlib.Path, required=True)
    ap.add_argument("--out-dir", type=pathlib.Path,
                    default=ROOT / "data" / "processed")
    ap.add_argument("--chosen-only", action="store_true", default=True,
                    help="keep only the source chosen per (trial, agent); see "
                         "extract/trial_dedup.py")
    ap.add_argument("--include-registry-overlap", action="store_true",
                    help="keep arms whose trial is already in the registry. Off by "
                         "default: those are the same patients, and admitting both gives "
                         "the trial double weight. On for the validation run, where the "
                         "overlap is the point.")
    ap.add_argument("--union", type=pathlib.Path, default=None,
                    help="also write the registry corpus unioned with these arms to this "
                         "directory, so `fit_forward.py --processed <dir>` refits on both. "
                         "The registry frames are the base; paper arms are appended.")
    ap.add_argument("--explicit-threshold-only", action="store_true",
                    help="the sensitivity refit: drop tables whose reporting cut was "
                         "derived from the minimum printed rate rather than stated")
    args = ap.parse_args()

    rows = [json.loads(ln) for ln in args.cells.read_text(encoding="utf-8").splitlines()
            if ln.strip()]
    if not rows:
        print("no cells to merge", file=sys.stderr)
        return 1
    cells = pd.DataFrame(rows)
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))["agents"]
    axes = list(default_taxonomy().axis_order)

    before = len(cells)
    if args.chosen_only:
        cells = cells[cells["is_chosen_source"]]
    if not args.include_registry_overlap:
        cells = cells[~cells["overlaps_registry"]]
    if args.explicit_threshold_only:
        cells = cells[cells["threshold_explicit"]]
    print(f"셀 {before} → {len(cells)} (중복 출처·레지스트리 중복·임계값 필터 적용)")
    if cells.empty:
        print("남은 셀이 없습니다", file=sys.stderr)
        return 1

    # An arm is a column of a table, so the key has to carry the table and the column.
    cells = cells.assign(
        arm_key=lambda d: (
            "PMC" + d["pmcid"].astype(str) + ":" + d["table_label"].astype(str)
            + ":" + d["column_header"].map(_header_key)
        ),
        kind=lambda d: d["caption_kind"] if "caption_kind" in d else "other",
    )
    # The severe tail is a third outcome table, not data to throw away. 112 of the 142
    # grade-restricted columns report grade 3 and above, which is the threshold clinical
    # practice acts on -- and `otherEvents` on ClinicalTrials.gov has no grade split at all,
    # so this table is literature-only. That makes it the clean form of the question the
    # corpus ablation asks: whether literature arms can support a model, with no registry
    # arms mixed in to carry it.
    #
    # The low-grade remainder -- "Grade 1-2", 30 columns -- stays out. A rate restricted to
    # the mild end is not an outcome anything would act on.
    # Mapped through Python's `re` rather than `str.contains`: the column is arrow-backed
    # and pyarrow's RE2 engine rejects a `\u` escape outright.
    severe = cells["column_header"].map(
        lambda h: bool(SEVERE_TAIL.search(str(h or "")))
        and column_outcome(h) == "grade_restricted"
    )
    cells.loc[severe, "kind"] = "grade3"

    arm_rows = []
    obs_rows = []
    for (arm_key, agent, kind), g in cells.groupby(["arm_key", "agent", "kind"]):
        spec = registry.get(agent)
        if spec is None:
            continue
        n_at_risk = int(g["denominator"].max())
        thr = g["threshold_pct"].dropna()
        nct = g["nct_id"].dropna().unique()
        arm_rows.append({
            "nct_id": (nct[0] if len(nct) else None),
            "group_id": arm_key,
            "arm_key": arm_key,
            "title": str(g["column_header"].iloc[0])[:160],
            "agent": agent,
            "layer": "literature",
            "is_monotherapy": True,       # combination columns are rejected upstream
            "is_comparator": False,
            "n_combo_agents": 0,
            "n_at_risk_other": (n_at_risk if kind == "other" else None),
            "n_at_risk_serious": (n_at_risk if kind == "serious" else None),
            "n_at_risk_grade3": (n_at_risk if kind == "grade3" else None),
            "n_at_risk": n_at_risk,
            "frequency_threshold": (float(thr.min()) if len(thr) else None),
            "threshold_is_upper_bound": bool(
                not g["threshold_explicit"].astype(bool).any()
            ),
            # Carried rather than dropped here, so the count is reportable and the arms
            # remain available to a severity-stratified outcome. `dataset.build` is what
            # keeps them out of the any-grade grid.
            "column_outcome": column_outcome(g["column_header"].iloc[0]),
            # Attribution rather than outcome: a column headed with a plural class of
            # agents is not the agent the title names.
            "agent_class_column": names_an_agent_class(g["column_header"].iloc[0]),
            "phase": None,
            "start_date": None,
            "results_posted": None,
            "source": "pmc",
            "pmcid": str(g["pmcid"].iloc[0]),
            "journal": str(g["journal"].iloc[0]),
            "license_code": g["license_code"].iloc[0],
            "attribution_gate": str(g["attribution_gate"].iloc[0]),
            **{c: spec.get(c) for c in DESIGN_COLS},
        })
        # The registry stores an axis as the maximum over its terms -- "any event in this
        # organ". Matching that is what makes paper and registry arms comparable.
        for axis, ga in g.groupby("axis"):
            obs_rows.append({
                "arm_key": arm_key,
                "nct_id": (nct[0] if len(nct) else None),
                "agent": agent,
                "axis": axis,
                "kind": kind,
                "n_affected": int(ga["n"].max()),
                "n_at_risk": n_at_risk,
                "sum_affected_terms": int(ga["n"].sum()),
                "n_terms": int(len(ga)),
                "frequency_threshold": (float(thr.min()) if len(thr) else None),
            })

    arms = pd.DataFrame(arm_rows)
    obs = pd.DataFrame(obs_rows)
    if arms.empty:
        print("팔이 만들어지지 않았습니다", file=sys.stderr)
        return 1

    unknown_axes = set(obs["axis"]) - set(axes)
    if unknown_axes:
        print(f"경고: 축 체계 밖의 축 {sorted(unknown_axes)}", file=sys.stderr)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    arms.to_parquet(args.out_dir / "paper_arms.parquet", index=False)
    obs.to_parquet(args.out_dir / "paper_observations.parquet", index=False)

    n_class = int(arms["agent_class_column"].sum())
    if n_class:
        print(f"  약물 클래스를 명명한 열 {n_class} / {len(arms)} 팔 — 귀속 불가로 제외됨")
    mism = arms["column_outcome"].value_counts().to_dict()
    off = {k: v for k, v in mism.items() if k != "any_grade"}
    if off:
        print(f"  전등급이 아닌 결과를 보고하는 열 {sum(off.values())} / {len(arms)} 팔"
              f" — 전등급 격자에서 제외됨: {off}")
    n_bound = int(arms["threshold_is_upper_bound"].sum())
    print(f"\n팔 {len(arms)}개, 약물 {arms['agent'].nunique()}종, "
          f"시험 {arms['nct_id'].nunique()}건, 관측 {len(obs)}개")
    print(f"  임계값이 상한인 팔 {n_bound}/{len(arms)} "
          f"({100.0 * n_bound / len(arms):.1f}%)   [계획서 실측 70.3%]")
    print(f"  팔당 축 중앙 {obs.groupby('arm_key').size().median():.0f} / {len(axes)}")
    print(f"  표 종류: {dict(arms.groupby('n_at_risk_other').size().head(0)) or ''}"
          f"other={int(arms['n_at_risk_other'].notna().sum())}, "
          f"serious={int(arms['n_at_risk_serious'].notna().sum())}")
    print("\n약물별 팔")
    for agent, n in arms["agent"].value_counts().items():
        print(f"  {agent:30s} {n:4d}")

    manifest = {
        "provenance": stamp({"cells": args.cells, "registry": REGISTRY}),
        "filters": {
            "chosen_only": args.chosen_only,
            "include_registry_overlap": args.include_registry_overlap,
            "explicit_threshold_only": args.explicit_threshold_only,
        },
        "n_cells_in": before,
        "n_cells_kept": int(len(cells)),
        "n_arms": int(len(arms)),
        "n_observations": int(len(obs)),
        "n_agents": int(arms["agent"].nunique()),
        "n_trials": int(arms["nct_id"].nunique()),
        "n_arms_threshold_upper_bound": n_bound,
        "arms_per_agent": arms["agent"].value_counts().to_dict(),
        "arms_per_gate": arms["attribution_gate"].value_counts().to_dict(),
    }
    (args.out_dir / "paper_corpus_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"\n→ {args.out_dir / 'paper_arms.parquet'}")
    print(f"→ {args.out_dir / 'paper_observations.parquet'}")

    if args.union:
        # The registry frames are the base and paper arms are appended, so a union is only
        # ever additive -- an existing analysis pointed at `data/processed` is unaffected,
        # and the comparison that matters is between two directories rather than between
        # two versions of one file.
        reg_arms = pd.read_parquet(ROOT / "data" / "processed" / "arms.parquet")
        reg_obs = pd.read_parquet(ROOT / "data" / "processed" / "observations.parquet")
        clash = set(reg_arms["arm_key"]) & set(arms["arm_key"])
        if clash:
            print(f"오류: arm_key가 겹칩니다 ({len(clash)}건) — union을 쓰지 않습니다",
                  file=sys.stderr)
            return 1
        u_arms = pd.concat([reg_arms, arms], ignore_index=True)
        u_obs = pd.concat([reg_obs, obs], ignore_index=True)
        args.union.mkdir(parents=True, exist_ok=True)
        u_arms.to_parquet(args.union / "arms.parquet", index=False)
        u_obs.to_parquet(args.union / "observations.parquet", index=False)
        n_reg_agents = reg_arms["agent"].nunique()
        n_union_agents = u_arms["agent"].nunique()
        print(f"\n합집합: 팔 {len(reg_arms)} + {len(arms)} = {len(u_arms)}, "
              f"약물 {n_reg_agents} → {n_union_agents}, "
              f"관측 {len(reg_obs)} + {len(obs)} = {len(u_obs)}")
        if n_union_agents == n_reg_agents:
            print("  주의: 새 약물 0종입니다. 설계 특징은 약물 단위 상수이므로 "
                  "식별 셀은 늘지 않습니다 — 늘어난 것은 약물별 프로파일의 정밀도뿐입니다.")
        print(f"→ {args.union / 'arms.parquet'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
