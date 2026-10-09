"""The DAR field is free text, and a parser over free text reads the wrong number.

`"2.7 in 2006 preclinical CR011-vcMMAE; not assumed clinical-product loading"` was parsed
as **1004.35**: a range heuristic saw the hyphen in the drug code and averaged 2.7 with the
year. Centred, that covariate reached +994 and froze the sampler -- zero-width posterior
intervals, a seed-agreement gap of 820 pooled standard deviations, and a failure that read
as non-convergence. Two twenty-minute fits to find. See negative result 47.

These tests pin the exact string that caused it, the shapes that must still parse, and the
builder's refusal to accept a covariate large enough to do it again.
"""

from __future__ import annotations

import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import merged_corpus_scale as M  # noqa: E402
from adctox.model import dataset as ds  # noqa: E402


def test_the_string_that_froze_the_sampler_is_refused() -> None:
    offender = ("2.7 in 2006 preclinical CR011-vcMMAE; not assumed clinical-product "
                "loading")
    assert M._first_number(offender) is None, (
        "the field says the figure is preclinical and must not be assumed to be the "
        "clinical loading; the right answer is no DAR, not 2.7 and certainly not 1004.35"
    )


@pytest.mark.parametrize("text,expected", [
    ("4", 4.0),
    ("3.5", 3.5),
    ("2 | 1.9 | 2 (nominal)", 2.0),
    ("3.5 ± 0.5", 3.5),
    ("2–3 | 2–3 mol/mol (Figure 6)", 2.5),
    ("7–8 | 7–8 SN-38 molecules per antibody", 7.5),
    ("Approximately 4", 4.0),
    ("Mean 2", 2.0),
    ("Average 4; reported range 1.7–5.1", 4.0),
    ("Target approximately 3.5 (Methods); measured average 3.6 (Results)", 3.5),
    ("4 (>95%)", 4.0),
])
def test_the_shapes_a_dar_is_actually_written_in_still_parse(text, expected) -> None:
    """The opposite failure matters too: a shape list that refuses a clear number loses an
    agent, and an agent is up to fourteen identifying cells."""
    assert M._first_number(text) == pytest.approx(expected)


@pytest.mark.parametrize("text", [
    "Not verified",
    "NA | NA (unconjugated antibody)",
    "4 and 8 compared in preclinical constructs; not a single clinical-product DAR",
    "Average 3 dyes/antibody in experimental cet-IR700; not confirmed clinical product",
    "Source literal: average drug:antibody ratio approximately 1:3.7; direction requires "
    "checking",
])
def test_fields_that_disclaim_their_own_number_are_refused(text) -> None:
    assert M._first_number(text) is None, text


def test_a_year_is_never_a_dar() -> None:
    """The specific shape of the original defect, generalised.

    Any four-digit number in a DAR field is a year, a catalogue number or a code, never a
    drug-to-antibody ratio. The sanity cap catches it whatever route it arrives by.
    """
    for text in ("2006", "2.7 in 2006", "DAR 2006", "1004.35"):
        got = M._first_number(text)
        assert got is None or got <= M.DAR_SANITY_CAP, (text, got)


def test_the_builder_refuses_a_covariate_large_enough_to_freeze_the_sampler() -> None:
    """The guard that makes this class of error loud instead of slow.

    Constructed directly rather than through a corpus: the point is that `build` refuses,
    names the arm and says the raw value, so the next parse error costs a traceback instead
    of two fits.
    """
    path = ROOT / "data" / "processed" / "arms.parquet"
    if not path.exists():
        pytest.skip("run `make corpus`")
    arms = pd.read_parquet(path)
    obs = pd.read_parquet(ROOT / "data" / "processed" / "observations.parquet")
    poisoned = arms.copy()
    i = poisoned.index[poisoned["dar"].notna()][0]
    poisoned.loc[i, "dar"] = 1004.35

    from adctox.taxonomy import Taxonomy
    with pytest.raises(ValueError) as excinfo:
        ds.build(poisoned, obs, list(Taxonomy().axis_order), kind="other")
    message = str(excinfo.value)
    assert "dar" in message
    # The diagnostic has to name the arm and the raw value, or it sends the reader back to
    # the sampler rather than to the parser.
    assert str(poisoned.loc[i, "agent"]) in message or "1004.35" in message
    assert "parse error" in message.lower()


def test_the_sanity_bound_admits_every_real_corpus() -> None:
    """A bound that would reject a legitimate corpus is worse than no bound."""
    from adctox.taxonomy import Taxonomy
    axes = list(Taxonomy().axis_order)
    for name in ("", "with_literature_final", "with_atlas"):
        p = ROOT / "data" / "processed" / name if name else ROOT / "data" / "processed"
        if not (p / "arms.parquet").exists():
            continue
        data = ds.load(p, axes, kind="other")
        for field in ("arm_dar_c", "arm_thresh_c", "arm_log_n_c"):
            v = np.asarray(getattr(data, field), dtype=float)
            assert np.abs(v).max() <= ds.COVARIATE_SANITY_BOUND, (name, field)


def test_the_parameter_count_follows_the_family_flag() -> None:
    """`n_free_parameters` read the module constant while `model` took an argument.

    So a fit run with `--payload-family` would have printed the parameter count, and
    therefore the identification ratio, of a fit without it -- and that ratio is the
    quantity the project's whole granularity argument rests on. The two now take the same
    argument.
    """
    path = ROOT / "data" / "processed" / "arms.parquet"
    if not path.exists():
        pytest.skip("run `make corpus`")
    from adctox.model import forward
    from adctox.taxonomy import Taxonomy
    data = ds.load(ROOT / "data" / "processed", list(Taxonomy().axis_order), kind="other")

    off = forward.n_free_parameters(data, use_family=False)
    on = forward.n_free_parameters(data, use_family=True)
    assert on["design"] - off["design"] == len(data.families) * len(data.axes), (
        off["design"], on["design"], len(data.families), len(data.axes)
    )
    # Enabling a level can only lower the ratio, because the cells do not change.
    assert on["design_ratio_vs_identifying"] < off["design_ratio_vs_identifying"]
    # And the default must still follow the module constant, so an unflagged fit is
    # unchanged by this plumbing.
    default = forward.n_free_parameters(data)
    expected = on if forward.USE_PAYLOAD_FAMILY else off
    assert default["design"] == expected["design"]
