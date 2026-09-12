"""A reference experiment plugin for tests.

The real experiment plugins cannot be exercised until the IACHY102 manual
is transcribed, but the machinery around them can. This plugin wires the
shared checker types exactly the way a real one will, so the Socratic
engine, the answer gate and the pipeline are all tested against a
realistic plugin rather than a mock.

The numbers here are arbitrary and are NOT from the manual. Nothing in
this module is registered, so it can never serve real traffic.
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

#: The value a correctly-worked run produces: 0.1 * 25.0 / 20.0
EXPECTED_FINAL_VALUE = 0.125

STUDENT_DATA: dict[str, Any] = {
    "standard_normality": 0.1,
    "standard_volume": 25.0,
    "titrant_volumes": [1, 2, 3, 4, 5, 6, 7, 8],
    "conductance": [10, 8, 6, 4, 6, 8, 10, 12],  # branches cross at 4.0
    "titre_volume": 20.0,
}

#: The endpoint the intersection geometry recovers from the data above.
EXPECTED_ENDPOINT = 4.0


def _final_formula(i: dict[str, Any]) -> float:
    return (i["standard_normality"] * i["standard_volume"]) / i["titre_volume"]


FINAL_CHECKER = DirectFormulaChecker(
    formula=_final_formula,
    required_inputs=("standard_normality", "standard_volume", "titre_volume"),
    tolerance=Tolerance(rel_tol=0.02),
    positive_inputs=("standard_normality", "standard_volume", "titre_volume"),
    nonzero_inputs=("titre_volume",),
    transposable_inputs=("standard_volume", "titre_volume"),
    label="normality of the unknown",
)

STANDARD_CHECKER = DirectFormulaChecker(
    formula=lambda i: i["standard_normality"] * i["standard_volume"],
    required_inputs=("standard_normality", "standard_volume"),
    tolerance=Tolerance(rel_tol=0.01),
    positive_inputs=("standard_normality", "standard_volume"),
    label="equivalents of standard",
)

ENDPOINT_CHECKER = EndpointDetectionChecker(
    x_key="titrant_volumes",
    y_key="conductance",
    geometry="intersection",
    tolerance=Tolerance(abs_tol=0.2),
    min_points=6,
    min_span=1.0,
    label="endpoint volume",
)

STEPS: tuple[StepSpec, ...] = (
    StepSpec(
        index=0,
        key="standardisation",
        prompt="Record the normality and volume of your standard solution.",
        requires=("standard_normality", "standard_volume"),
        hints=(
            "Check the label on the standard solution again.",
            "The normality you entered is not the one on the bottle you used.",
            "You have put the unknown's volume in the standard's field.",
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
            "Your two straight portions do not meet where you marked it.",
            "The readings either side of the turn are too widely spaced.",
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
            "One of your volumes is on the wrong side of the relationship.",
            "Your arithmetic is off by a factor of ten -- a unit conversion.",
        ),
        is_final=True,
    ),
)


def reference_plugin() -> DeterministicPlugin:
    return DeterministicPlugin(
        id="ref01",
        title="Reference titration (test fixture, not from the manual)",
        manual_reference="n/a -- test fixture",
        checker=FINAL_CHECKER,
        step_specs=STEPS,
        step_checkers={
            0: STANDARD_CHECKER,
            1: ENDPOINT_CHECKER,
            2: FINAL_CHECKER,
        },
    )


#: The value each step expects, for driving the engine through a full run.
STEP_ANSWERS = {
    0: STUDENT_DATA["standard_normality"] * STUDENT_DATA["standard_volume"],
    1: EXPECTED_ENDPOINT,
    2: EXPECTED_FINAL_VALUE,
}
