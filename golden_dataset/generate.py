"""Generate the Category 2 known-deviation dataset.

Each case is synthetic data constructed to trigger exactly one Tier 1
signature-detection rule, against a reference checker configuration that
uses the same shared checker types the real experiment plugins will use.

Running this script regenerates `category2_known_deviations/cases.json`
and verifies, for every case, that the intended rule actually fires. A
case that does not trigger its own rule is a bug in the case or in the
rule, and this script fails rather than writing it out (AGENTS.md,
`test-builder`).

Usage:  python golden_dataset/generate.py
"""

from __future__ import annotations

import json
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))

from backend.tier1_compute.shared import (  # noqa: E402
    CalibrationCurveChecker,
    DirectFormulaChecker,
    EndpointDetectionChecker,
    Outcome,
    RegressionSlopeChecker,
    Tolerance,
)

# ---------------------------------------------------------------------------
# Reference checker configurations
#
# These stand in for real experiment plugins so the signature rules can be
# exercised before the manual is transcribed. The numbers are ARBITRARY --
# they are not from BACHY105 and must never be copied into a plugin.
# ---------------------------------------------------------------------------


def _normality(i: dict) -> float:
    return (i["n1"] * i["v1"]) / i["v2"]


DIRECT = DirectFormulaChecker(
    formula=_normality,
    required_inputs=("n1", "v1", "v2"),
    tolerance=Tolerance(rel_tol=0.02),
    positive_inputs=("n1", "v1", "v2"),
    nonzero_inputs=("v2",),
    transposable_inputs=("v1", "v2"),
    label="reference direct-formula config",
)

CALIBRATION = CalibrationCurveChecker(
    standards_x_key="conc",
    standards_y_key="absorbance",
    unknown_y_key="unknown_abs",
    tolerance=Tolerance(rel_tol=0.05),
    min_r_squared=0.99,
    min_standards=3,
    label="reference calibration-curve config",
)

PEAK = EndpointDetectionChecker(
    x_key="volume",
    y_key="dEdV",
    geometry="peak",
    tolerance=Tolerance(abs_tol=0.2),
    min_points=5,
    max_increment=1.0,
    min_prominence=5.0,
    label="reference peak-endpoint config",
)

INTERSECTION = EndpointDetectionChecker(
    x_key="volume",
    y_key="conductance",
    geometry="intersection",
    tolerance=Tolerance(abs_tol=0.3),
    min_points=6,
    min_span=1.0,
    label="reference intersection-endpoint config",
)

REGRESSION = RegressionSlopeChecker(
    x_key="t",
    y_key="conc",
    tolerance=Tolerance(rel_tol=0.05),
    min_r_squared=0.98,
    transform_y=math.log,
    slope_to_value=lambda s: -s,
    min_points=4,
    expect_direction="decreasing",
    label="reference regression-slope config",
)

CHECKERS = {
    "direct_formula": DIRECT,
    "calibration_curve": CALIBRATION,
    "endpoint_peak": PEAK,
    "endpoint_intersection": INTERSECTION,
    "regression_slope": REGRESSION,
}

_FIRST_ORDER_TIMES = [0, 10, 20, 30, 40, 50]
_FIRST_ORDER_CONC = [round(math.exp(-0.05 * t), 6) for t in _FIRST_ORDER_TIMES]


def cases() -> list[dict]:
    return [
        {
            "id": "c2-sign-flip",
            "signature": "sign_flip",
            "checker": "regression_slope",
            "description": (
                "Rate constant reported with the wrong sign -- the slope-to-"
                "constant conversion was not negated."
            ),
            "inputs": {"t": _FIRST_ORDER_TIMES, "conc": _FIRST_ORDER_CONC},
            "reported": -0.05,
        },
        {
            "id": "c2-unit-scale",
            "signature": "unit_scale_error",
            "checker": "direct_formula",
            "description": "Right arithmetic, wrong scale: reported ten times too large.",
            "inputs": {"n1": 0.1, "v1": 25.0, "v2": 20.0},
            "reported": 1.25,
        },
        {
            "id": "c2-transposed-inputs",
            "signature": "transposed_inputs",
            "checker": "direct_formula",
            "description": (
                "The two volumes were recorded against the wrong labels; "
                "recomputing with them swapped reproduces the reported value."
            ),
            "inputs": {"n1": 0.1, "v1": 25.0, "v2": 20.0},
            "reported": 0.08,
        },
        {
            "id": "c2-rounding-drift",
            "signature": "rounding_drift",
            "checker": "direct_formula",
            "description": "Just outside tolerance, consistent with early rounding.",
            "inputs": {"n1": 0.1, "v1": 25.0, "v2": 20.0},
            "reported": 0.13,
        },
        {
            "id": "c2-poor-linear-fit",
            "signature": "poor_linear_fit",
            "checker": "calibration_curve",
            "description": "Calibration standards scatter badly; R^2 below the floor.",
            "inputs": {
                "conc": [1, 2, 3, 4, 5],
                "absorbance": [0.1, 0.5, 0.15, 0.9, 0.2],
                "unknown_abs": 0.25,
            },
            "reported": 2.5,
        },
        {
            "id": "c2-extrapolation",
            "signature": "extrapolated_beyond_standards",
            "checker": "calibration_curve",
            "description": "The unknown reads outside the range the standards cover.",
            "inputs": {
                "conc": [1, 2, 3],
                "absorbance": [0.1, 0.2, 0.3],
                "unknown_abs": 0.9,
            },
            "reported": 9.0,
        },
        {
            "id": "c2-non-monotonic",
            "signature": "non_monotonic_data",
            "checker": "calibration_curve",
            "description": (
                "Two adjacent standards were transcribed into each other's "
                "rows. A long series is used deliberately: in a short "
                "calibration a single transposition also drags R^2 under the "
                "floor, so the fit-quality rule fires first and this rule is "
                "unreachable. That ordering is correct -- an unusable "
                "calibration is the more important finding -- but it means "
                "isolating the monotonicity rule needs enough points that one "
                "swap leaves the fit intact."
            ),
            "inputs": {
                "conc": list(range(1, 17)),
                "absorbance": [
                    0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.45,
                    0.40, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80,
                ],
                "unknown_abs": 0.25,
            },
            "reported": 5.0,
        },
        {
            "id": "c2-unresolved-peak",
            "signature": "unresolved_peak",
            "checker": "endpoint_peak",
            "description": (
                "A broad, shallow EMF peak: a maximum exists but stands too "
                "little above baseline to locate an endpoint."
            ),
            "inputs": {
                "volume": [8.0, 8.5, 9.0, 9.5, 10.0],
                "dEdV": [2.0, 2.5, 3.0, 2.6, 2.1],
            },
            "reported": 9.0,
        },
        {
            "id": "c2-coarse-increments",
            "signature": "coarse_increments",
            "checker": "endpoint_peak",
            "description": (
                "The EMF titration was run in 5 mL steps, far too coarse to "
                "resolve the endpoint even though a sharp peak is present."
            ),
            "inputs": {
                "volume": [0.0, 5.0, 10.0, 15.0, 20.0],
                "dEdV": [2.0, 5.0, 40.0, 6.0, 2.0],
            },
            "reported": 10.0,
        },
        {
            "id": "c2-flat-response",
            "signature": "flat_response",
            "checker": "endpoint_intersection",
            "description": "Conductance barely moves; no endpoint exists in this data.",
            "inputs": {
                "volume": [1, 2, 3, 4, 5, 6],
                "conductance": [5.0, 5.1, 5.0, 5.05, 5.0, 5.1],
            },
            "reported": 3.0,
        },
        {
            "id": "c2-insufficient-points",
            "signature": "insufficient_points",
            "checker": "regression_slope",
            "description": "Too few readings to fit a defensible slope.",
            "inputs": {"t": [0, 10, 20], "conc": [1.0, 0.606, 0.367]},
            "reported": 0.05,
        },
    ]


def verify(case: dict) -> tuple[bool, str]:
    checker = CHECKERS[case["checker"]]
    result = checker.check(case["inputs"], case["reported"])

    if case["signature"] == "insufficient_points":
        # This one surfaces as a validation error before a signature can be
        # produced, which is the correct behaviour: too few points is a data
        # problem, not a diagnosis.
        if result.outcome is Outcome.INVALID and any(
            "at least" in e for e in result.errors
        ):
            return True, "invalid (too few points), as intended"
        return False, f"expected INVALID, got {result.outcome.value}"

    if result.outcome not in (Outcome.FAIL_WITH_SIGNATURE,):
        return False, f"expected a signature, got {result.outcome.value}"
    if result.signature_code != case["signature"]:
        return False, f"expected '{case['signature']}', got '{result.signature_code}'"
    return True, "ok"


def main() -> int:
    out_dir = ROOT / "category2_known_deviations"
    out_dir.mkdir(exist_ok=True)

    all_cases = cases()
    failures: list[str] = []
    records = []

    for case in all_cases:
        ok, note = verify(case)
        status = "verified" if ok else "FAILED"
        print(f"  {case['id']:28s} {case['signature']:32s} {status}: {note}")
        if not ok:
            failures.append(f"{case['id']}: {note}")
        records.append(case | {"verified": ok, "verification_note": note})

    if failures:
        print("\nRefusing to write the dataset. Cases that did not trigger their rule:")
        for f in failures:
            print(f"  - {f}")
        return 1

    payload = {
        "category": 2,
        "title": "Known-deviation cases per Tier 1 signature",
        "note": (
            "Synthetic data, not manual-sourced. Numbers here are arbitrary "
            "and exist only to trigger a specific detection rule; they are "
            "NOT BACHY105 values and must not be copied into an experiment "
            "plugin."
        ),
        "reference_checkers": {
            name: type(checker).__name__ for name, checker in CHECKERS.items()
        },
        "cases": records,
    }
    (out_dir / "cases.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\nWrote {len(records)} verified cases to {out_dir / 'cases.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
