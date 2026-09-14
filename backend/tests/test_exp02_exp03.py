"""Experiments 2 and 3 -- synthetic self-consistency checks.

Neither experiment has a manual-printed worked example (see
manual/IACHY102_manual.md's summary table), so unlike exp01 there is no
Category 1 golden case here. These are the "leave one runnable check"
tests for the new checker wiring itself: synthetic data constructed by
inverting the manual's own formula, not manual-sourced ground truth.
"""

from __future__ import annotations

import math

import pytest

from backend.tier1_compute.experiments import get_plugin
from backend.tier1_compute.experiments.exp02 import FINAL_CHECKER as EXP02_CHECKER
from backend.tier1_compute.experiments.exp03 import FINAL_CHECKER as EXP03_CHECKER
from backend.tier1_compute.shared.types import Outcome

# --- Experiment 2: ester hydrolysis rate constant ---------------------------

_V_INF = 50.0
_V0 = 5.0
_K1_TRUE = 0.02  # min^-1, chosen for this synthetic series
_TS = [0, 10, 20, 30, 40, 50, 60]
_VTS = [_V_INF - (_V_INF - _V0) * math.exp(-_K1_TRUE * t) for t in _TS]


def test_exp02_recomputes_the_rate_constant_from_synthetic_data():
    result = EXP02_CHECKER.check(
        {
            "time_min": _TS,
            "titre_volume_ml": _VTS,
            "titre_volume_at_completion_ml": _V_INF,
        },
        reported=_K1_TRUE,
    )
    assert result.outcome is Outcome.PASS
    assert result.expected_value == pytest.approx(_K1_TRUE, rel=0.02)


def test_exp02_flags_a_wrong_rate_constant():
    result = EXP02_CHECKER.check(
        {
            "time_min": _TS,
            "titre_volume_ml": _VTS,
            "titre_volume_at_completion_ml": _V_INF,
        },
        reported=0.2,  # 10x too large
    )
    assert not result.passed


def test_exp02_plugin_final_step_is_wired():
    """Regression test for the missing-final-step-checker bug class found
    in exp01 during this session -- confirm exp02's is present too."""
    plugin = get_plugin("exp02")
    result = plugin.check_step(
        1,
        {
            "time_min": _TS,
            "titre_volume_ml": _VTS,
            "titre_volume_at_completion_ml": _V_INF,
        },
        submitted=_K1_TRUE,
    )
    assert result.outcome is Outcome.PASS


# --- Experiment 3: Ni2+ colorimetry -----------------------------------------

_STD_CONC = [2, 4, 6, 8]
_SLOPE = 0.05
_STD_ABS = [_SLOPE * c for c in _STD_CONC]


def test_exp03_reads_the_unknown_off_the_calibration_line():
    result = EXP03_CHECKER.check(
        {
            "standard_conc_ppm": _STD_CONC,
            "standard_absorbance": _STD_ABS,
            "unknown_absorbance": 0.25,
        },
        reported=5.0,
    )
    assert result.outcome is Outcome.PASS
    assert result.expected_value == pytest.approx(5.0, rel=0.01)


def test_exp03_flags_extrapolation_beyond_the_standards():
    result = EXP03_CHECKER.check(
        {
            "standard_conc_ppm": _STD_CONC,
            "standard_absorbance": _STD_ABS,
            "unknown_absorbance": 5.0,  # way above the 8ppm standard's 0.4
        },
        reported=100.0,
    )
    assert result.signature_code == "extrapolated_beyond_standards"


def test_exp03_plugin_final_step_is_wired():
    plugin = get_plugin("exp03")
    result = plugin.check_step(
        1,
        {
            "standard_conc_ppm": _STD_CONC,
            "standard_absorbance": _STD_ABS,
            "unknown_absorbance": 0.25,
        },
        submitted=5.0,
    )
    assert result.outcome is Outcome.PASS


if __name__ == "__main__":
    test_exp02_recomputes_the_rate_constant_from_synthetic_data()
    test_exp02_flags_a_wrong_rate_constant()
    test_exp02_plugin_final_step_is_wired()
    test_exp03_reads_the_unknown_off_the_calibration_line()
    test_exp03_flags_extrapolation_beyond_the_standards()
    test_exp03_plugin_final_step_is_wired()
    print("exp02/exp03 self-check OK")
