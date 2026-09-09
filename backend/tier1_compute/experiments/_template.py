"""Worked reference for writing a per-experiment Tier 1 plugin.

Deliberately NOT registered: the numbers below are illustrative and are
not from the BACHY105 manual. Copy this file to `expNN.py`, replace every
value with the manual's own, and call `register(...)` there.

The point of the plugin system is that a new experiment is *configuration*
-- a formula, a tolerance, some detector thresholds and an ordered list of
steps. If you find yourself writing loops or arithmetic in a plugin file,
that logic belongs in a shared checker type instead (AGENTS.md,
`tier1-compute-builder`).
"""

from __future__ import annotations

from typing import Any

from backend.tier1_compute.experiments.registry import DeterministicPlugin
from backend.tier1_compute.shared import (
    DirectFormulaChecker,
    EndpointDetectionChecker,
    StepSpec,
    Tolerance,
)

EXPERIMENT_ID = "_template"


# --- 1. The manual's formula, transcribed exactly --------------------------
# Keep it a pure function of the student's own inputs. Every symbol should
# be traceable to a symbol in the manual.
def _normality_of_unknown(i: dict[str, Any]) -> float:
    """N2 = (N1 * V1) / V2  -- ILLUSTRATIVE, not from the manual."""
    return (i["standard_normality"] * i["standard_volume"]) / i["titre_volume"]


# --- 2. The final-result checker -------------------------------------------
FINAL_CHECKER = DirectFormulaChecker(
    formula=_normality_of_unknown,
    required_inputs=("standard_normality", "standard_volume", "titre_volume"),
    # Tolerance comes from the manual's stated acceptance band. Never
    # widen it to make a test pass.
    tolerance=Tolerance(rel_tol=0.02),
    positive_inputs=("standard_normality", "standard_volume", "titre_volume"),
    nonzero_inputs=("titre_volume",),
    # Enable only the detectors that describe real mistakes in THIS
    # experiment. An irrelevant detector produces confident nonsense.
    transposable_inputs=("standard_volume", "titre_volume"),
    check_unit_scale=True,
    check_rounding=True,
    label="normality of the unknown",
)


# --- 3. Per-step checkers for Socratic mode --------------------------------
# Each verifies ONE intermediate quantity against the student's own data.
# None of them computes the final answer.
STEP_CHECKERS = {
    1: EndpointDetectionChecker(
        x_key="titrant_volumes",
        y_key="conductance",
        geometry="intersection",
        tolerance=Tolerance(abs_tol=0.2),
        min_points=6,
        min_span=1.0,
        label="endpoint volume",
    ),
}


# --- 4. The ordered procedure, from the manual -----------------------------
# The hint ladder goes vague -> specific -> names the likely issue. No rung
# may contain the numeric answer; the test suite asserts this structurally.
STEPS: tuple[StepSpec, ...] = (
    StepSpec(
        index=0,
        key="standardisation",
        prompt="Record the normality and volume of your standard solution.",
        requires=("standard_normality", "standard_volume"),
        hints=(
            "Check the label on the standard solution again.",
            "The normality you have entered is not the one written on the "
            "bottle you used.",
            "You have recorded the unknown's volume in the standard's field -- "
            "the two are swapped.",
        ),
    ),
    StepSpec(
        index=1,
        key="endpoint",
        prompt="Plot your readings and report the endpoint volume.",
        requires=("titrant_volumes", "conductance"),
        tolerance=Tolerance(abs_tol=0.2),
        hints=(
            "Look at the shape of your plot around the turning point.",
            "Your two straight portions do not meet where you have marked the "
            "endpoint -- check where the fitted lines actually cross.",
            "The readings either side of the turn are too widely spaced to "
            "locate the endpoint; that part of the titration needs repeating.",
        ),
    ),
    StepSpec(
        index=2,
        key="final_normality",
        prompt="Calculate the normality of the unknown from your endpoint.",
        requires=("standard_normality", "standard_volume", "titre_volume"),
        tolerance=Tolerance(rel_tol=0.02),
        hints=(
            "Check which volume belongs in which position of the formula.",
            "Re-read the relationship between the two solutions -- one of your "
            "volumes is on the wrong side.",
            "Your arithmetic is off by a factor of ten, which is a unit "
            "conversion rather than a mistake in the titration.",
        ),
        is_final=True,
    ),
)


# --- 5. Registration -------------------------------------------------------
# A real plugin calls register(...) at import time. This template does not,
# so its illustrative numbers can never reach a student.
EXAMPLE_PLUGIN = DeterministicPlugin(
    id=EXPERIMENT_ID,
    title="Template (not a real experiment)",
    manual_reference="n/a -- illustrative only",
    checker=FINAL_CHECKER,
    step_specs=STEPS,
    step_checkers=STEP_CHECKERS,
)
