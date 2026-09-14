"""Experiment 1 (Zn-Cu EMF/thermodynamics) against the manual's own numbers.

Category 1 (golden_dataset/category1_worked_examples/exp01.json) already
covers the final Delta-G checker via the generic harness. This file
additionally checks the Nernst-equation step checker, which that harness
does not reach, and the plugin end-to-end through `check`/`check_step`.
"""

from __future__ import annotations

import pytest

from backend.tier1_compute.experiments import get_plugin
from backend.tier1_compute.experiments.exp01 import ECELL_CHECKER
from backend.tier1_compute.shared.types import Outcome


def test_nernst_step_matches_manual_worked_example():
    """p.13: [Zn2+]=0.05M, [Cu2+]=0.01M, T=303K -> Ecell = 1.079 V."""
    result = ECELL_CHECKER.check(
        {"zn_conc": 0.05, "cu_conc": 0.01, "temperature_k": 303},
        reported=1.079,
    )
    assert result.outcome is Outcome.PASS
    assert result.expected_value == pytest.approx(1.079, abs=1e-3)


def test_nernst_step_flags_a_swapped_ratio():
    """Swapping [Zn2+] and [Cu2+] flips the sign of the log term."""
    result = ECELL_CHECKER.check(
        {"zn_conc": 0.01, "cu_conc": 0.05, "temperature_k": 303},
        reported=1.079,
    )
    assert not result.passed


def test_plugin_final_check_matches_manual_delta_g():
    """p.13: n=2, F=96500, Ecell=0.99V -> Delta-G = -191 kJ/mol at 30C."""
    plugin = get_plugin("exp01")
    result = plugin.check({"ecell": 0.99}, reported=-191.0)
    assert result.outcome is Outcome.PASS


def test_plugin_step_zero_is_the_ecell_measurement_not_the_final_answer():
    """Socratic mode must never leak Delta-G through the intermediate step."""
    plugin = get_plugin("exp01")
    result = plugin.check_step(
        0, {"zn_conc": 0.05, "cu_conc": 0.01, "temperature_k": 303}, submitted=1.079
    )
    assert result.outcome is Outcome.PASS
    assert result.expected_value == pytest.approx(1.079, abs=1e-3)


if __name__ == "__main__":
    test_nernst_step_matches_manual_worked_example()
    test_nernst_step_flags_a_swapped_ratio()
    test_plugin_final_check_matches_manual_delta_g()
    test_plugin_step_zero_is_the_ecell_measurement_not_the_final_answer()
    print("exp01 self-check OK")
