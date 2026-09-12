"""Deterministic deviation-signature detectors.

Each detector answers one narrow question about numbers and returns
either a `SignatureHit` or None. They are pure functions: same input,
same verdict, every time, with no model in the loop. That is what makes
Tier 1 auditable -- a professor can reproduce any diagnosis by hand.

Detectors are shared across experiments; a per-experiment plugin picks
which ones apply and with what thresholds.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Callable, Sequence

import numpy as np

from backend.tier1_compute.shared.types import SignatureHit, Tolerance

# ---------------------------------------------------------------------------
# Linear algebra helpers
# ---------------------------------------------------------------------------


class FitResult:
    __slots__ = ("slope", "intercept", "r_squared", "n")

    def __init__(self, slope: float, intercept: float, r_squared: float, n: int) -> None:
        self.slope = slope
        self.intercept = intercept
        self.r_squared = r_squared
        self.n = n

    def predict(self, x: float) -> float:
        return self.slope * x + self.intercept

    def solve_for_x(self, y: float) -> float:
        if self.slope == 0.0:
            return math.nan
        return (y - self.intercept) / self.slope

    def as_dict(self) -> dict:
        return {
            "slope": self.slope,
            "intercept": self.intercept,
            "r_squared": self.r_squared,
            "n": self.n,
        }


def least_squares_fit(x: Sequence[float], y: Sequence[float]) -> FitResult:
    """Ordinary least squares for y = mx + c, plus R^2."""
    xa = np.asarray(x, dtype=float)
    ya = np.asarray(y, dtype=float)
    if xa.size != ya.size:
        raise ValueError("x and y must be the same length")
    if xa.size < 2:
        raise ValueError("need at least two points to fit a line")
    if np.ptp(xa) == 0.0:
        raise ValueError("x values are all identical; slope is undefined")

    slope, intercept = np.polyfit(xa, ya, 1)
    predicted = slope * xa + intercept
    ss_res = float(np.sum((ya - predicted) ** 2))
    ss_tot = float(np.sum((ya - np.mean(ya)) ** 2))
    r_squared = 1.0 if ss_tot == 0.0 else 1.0 - ss_res / ss_tot
    return FitResult(float(slope), float(intercept), float(r_squared), int(xa.size))


# ---------------------------------------------------------------------------
# Result-shape signatures (expected vs reported)
# ---------------------------------------------------------------------------


def detect_sign_flip(expected: float, reported: float, tol: Tolerance) -> SignatureHit | None:
    """Reported value matches the expected magnitude with the wrong sign.

    In potentiometry this is the classic swapped-electrode signature.
    """
    if expected == 0.0 or reported == 0.0:
        return None
    if (expected > 0) == (reported > 0):
        return None
    if not tol.matches(abs(expected), abs(reported)):
        return None
    return SignatureHit(
        code="sign_flip",
        detail=(
            "The reported magnitude is correct but the sign is inverted, "
            "which is what a reversed polarity/electrode assignment produces."
        ),
        evidence={"expected": expected, "reported": reported},
    )


def detect_unit_scale_error(
    expected: float,
    reported: float,
    tol: Tolerance,
    factors: Sequence[float] = (1e-6, 1e-3, 1e-2, 1e-1, 10.0, 100.0, 1e3, 1e6),
) -> SignatureHit | None:
    """Reported value is the right number at the wrong scale (mL vs L, g vs mg)."""
    if expected == 0.0 or not math.isfinite(reported):
        return None
    for f in factors:
        if tol.matches(expected * f, reported):
            return SignatureHit(
                code="unit_scale_error",
                detail=(
                    f"The reported value is off by a factor of {f:g}, which is a "
                    "unit-conversion error rather than a measurement problem."
                ),
                evidence={"expected": expected, "reported": reported, "factor": f},
            )
    return None


def detect_transposed_inputs(
    formula: Callable[[dict[str, float]], float],
    inputs: dict[str, float],
    reported: float,
    tol: Tolerance,
    candidate_keys: Sequence[str] | None = None,
) -> SignatureHit | None:
    """Recomputing with two inputs swapped reproduces the reported value.

    Catches values entered against the wrong solution/label.
    """
    keys = list(candidate_keys) if candidate_keys else [
        k for k, v in inputs.items() if isinstance(v, (int, float))
    ]
    for a, b in itertools.combinations(keys, 2):
        if a not in inputs or b not in inputs:
            continue
        if inputs[a] == inputs[b]:
            continue
        swapped = dict(inputs)
        swapped[a], swapped[b] = inputs[b], inputs[a]
        try:
            value = float(formula(swapped))
        except Exception:
            continue
        if math.isfinite(value) and tol.matches(value, reported):
            return SignatureHit(
                code="transposed_inputs",
                detail=(
                    f"Recomputing with '{a}' and '{b}' exchanged reproduces the "
                    "reported result exactly, so those two values were most "
                    "likely recorded against the wrong labels."
                ),
                evidence={"swapped": [a, b], "value_when_swapped": value},
            )
    return None


def detect_rounding_drift(
    expected: float, reported: float, tol: Tolerance, loose_factor: float = 5.0
) -> SignatureHit | None:
    """Just outside tolerance, but within a small multiple of it.

    Distinguishes premature rounding from a real procedural error.
    """
    if tol.matches(expected, reported):
        return None
    loose = Tolerance(
        abs_tol=None if tol.abs_tol is None else tol.abs_tol * loose_factor,
        rel_tol=None if tol.rel_tol is None else tol.rel_tol * loose_factor,
    )
    if not loose.matches(expected, reported):
        return None
    return SignatureHit(
        code="rounding_drift",
        detail=(
            "The result misses tolerance by only a small margin, consistent "
            "with rounding intermediate values too early rather than with a "
            "mistake in the procedure."
        ),
        evidence={"expected": expected, "reported": reported},
    )


# ---------------------------------------------------------------------------
# Raw-data-shape signatures
# ---------------------------------------------------------------------------


def detect_insufficient_points(
    xs: Sequence[float], minimum: int
) -> SignatureHit | None:
    if len(xs) >= minimum:
        return None
    return SignatureHit(
        code="insufficient_points",
        detail=(
            f"Only {len(xs)} readings were recorded; this experiment needs at "
            f"least {minimum} for the result to be determinable."
        ),
        evidence={"n": len(xs), "minimum": minimum},
    )


def detect_non_monotonic(
    ys: Sequence[float], expect: str = "increasing", allowance: float = 0.0
) -> SignatureHit | None:
    """Series reverses direction where the procedure implies it should not."""
    arr = np.asarray(ys, dtype=float)
    if arr.size < 3:
        return None
    diffs = np.diff(arr)
    if expect == "increasing":
        violations = np.where(diffs < -abs(allowance))[0]
    elif expect == "decreasing":
        violations = np.where(diffs > abs(allowance))[0]
    else:
        raise ValueError("expect must be 'increasing' or 'decreasing'")
    if violations.size == 0:
        return None
    return SignatureHit(
        code="non_monotonic_data",
        detail=(
            f"The response is expected to be monotonically {expect}, but it "
            f"reverses direction at {violations.size} point(s). That usually "
            "means readings were taken out of order or transcribed into the "
            "wrong rows."
        ),
        evidence={
            "reversal_indices": [int(i) + 1 for i in violations],
            "expected_direction": expect,
        },
    )


def detect_flat_response(ys: Sequence[float], min_span: float) -> SignatureHit | None:
    """The measured quantity barely moves across the run."""
    arr = np.asarray(ys, dtype=float)
    if arr.size == 0:
        return None
    span = float(np.ptp(arr))
    if span >= min_span:
        return None
    return SignatureHit(
        code="flat_response",
        detail=(
            f"The measured response varies by only {span:g} across the whole "
            "run, so no endpoint can be located in this data at all."
        ),
        evidence={"span": span, "min_span": min_span},
    )


def detect_coarse_increments(
    xs: Sequence[float], max_spacing: float
) -> SignatureHit | None:
    """Steps near the endpoint are too wide to resolve it.

    This is the "coarse increments" path: the data is not wrong, it is
    too sparse for the endpoint to be located to the required precision.
    """
    arr = np.asarray(sorted(float(x) for x in xs), dtype=float)
    if arr.size < 2:
        return None
    spacings = np.diff(arr)
    worst = float(np.max(spacings))
    if worst <= max_spacing:
        return None
    return SignatureHit(
        code="coarse_increments",
        detail=(
            f"The largest gap between successive readings is {worst:g}, wider "
            f"than the {max_spacing:g} needed to resolve the endpoint. The run "
            "needs repeating with finer increments through the transition."
        ),
        evidence={"max_observed_spacing": worst, "max_allowed_spacing": max_spacing},
    )


def detect_unresolved_peak(
    xs: Sequence[float],
    ys: Sequence[float],
    min_prominence: float,
) -> SignatureHit | None:
    """A peak exists but is too broad/shallow to pin down an endpoint."""
    x = np.asarray(xs, dtype=float)
    y = np.asarray(ys, dtype=float)
    if x.size < 3:
        return None
    peak_idx = int(np.argmax(y))
    prominence = float(y[peak_idx] - np.median(y))
    if prominence >= min_prominence:
        return None
    return SignatureHit(
        code="unresolved_peak",
        detail=(
            f"The maximum stands only {prominence:g} above the baseline, below "
            f"the {min_prominence:g} needed to call it a resolved peak. The "
            "endpoint read off this curve is not trustworthy."
        ),
        evidence={
            "prominence": prominence,
            "min_prominence": min_prominence,
            "peak_at_x": float(x[peak_idx]),
        },
    )


def detect_poor_linear_fit(
    xs: Sequence[float], ys: Sequence[float], min_r_squared: float
) -> SignatureHit | None:
    try:
        fit = least_squares_fit(xs, ys)
    except ValueError:
        return None
    if fit.r_squared >= min_r_squared:
        return None
    return SignatureHit(
        code="poor_linear_fit",
        detail=(
            f"The calibration points give R^2 = {fit.r_squared:.4f}, below the "
            f"{min_r_squared:g} this experiment requires. A line fitted to this "
            "scatter cannot be used to read off the unknown."
        ),
        evidence=fit.as_dict() | {"min_r_squared": min_r_squared},
    )


def detect_extrapolation(
    standards_x: Sequence[float], unknown_x: float
) -> SignatureHit | None:
    """The unknown falls outside the range the standards actually cover."""
    arr = np.asarray(standards_x, dtype=float)
    if arr.size == 0 or not math.isfinite(unknown_x):
        return None
    lo, hi = float(np.min(arr)), float(np.max(arr))
    if lo <= unknown_x <= hi:
        return None
    return SignatureHit(
        code="extrapolated_beyond_standards",
        detail=(
            f"The unknown reads at {unknown_x:g}, outside the calibrated range "
            f"[{lo:g}, {hi:g}]. The result is an extrapolation, not a "
            "measurement the standards support."
        ),
        evidence={"unknown": unknown_x, "range": [lo, hi]},
    )


def detect_endpoint_outside_range(
    xs: Sequence[float], endpoint_x: float
) -> SignatureHit | None:
    arr = np.asarray(xs, dtype=float)
    if arr.size == 0 or not math.isfinite(endpoint_x):
        return None
    lo, hi = float(np.min(arr)), float(np.max(arr))
    if lo <= endpoint_x <= hi:
        return None
    return SignatureHit(
        code="endpoint_outside_data_range",
        detail=(
            f"The two fitted branches meet at {endpoint_x:g}, outside the range "
            f"actually measured [{lo:g}, {hi:g}]. The titration was stopped "
            "before the endpoint was reached."
        ),
        evidence={"endpoint": endpoint_x, "range": [lo, hi]},
    )
