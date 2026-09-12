"""Checker type: calibration-curve experiments.

Fit a line to a set of standards, then read an unknown off that fit.
Used for colorimetry/conductometry-style experiments where the answer is
only as good as the calibration behind it -- so most of the diagnostic
value is in the fit quality, not the final arithmetic.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from backend.tier1_compute.shared.base import Checker
from backend.tier1_compute.shared import signatures
from backend.tier1_compute.shared.types import SignatureHit, Tolerance


class CalibrationCurveChecker(Checker):
    """Fit standards, solve for the unknown, compare to the reported value.

    Args:
        standards_x_key / standards_y_key: keys holding the standards'
            concentration and response series.
        unknown_y_key: key holding the unknown's measured response.
        min_r_squared: the manual's fit-quality floor.
        min_standards: minimum number of standards the method requires.
        solve_for: "x" reads a concentration off a measured response
            (the usual direction); "y" predicts a response.
        scale: multiplier applied to the solved value (e.g. a dilution
            factor from the manual).
    """

    def __init__(
        self,
        *,
        standards_x_key: str,
        standards_y_key: str,
        unknown_y_key: str,
        tolerance: Tolerance,
        min_r_squared: float,
        min_standards: int = 3,
        solve_for: str = "x",
        scale: float = 1.0,
        label: str = "",
    ) -> None:
        super().__init__(
            required_inputs=(standards_x_key, standards_y_key, unknown_y_key),
            tolerance=tolerance,
            label=label,
        )
        self.standards_x_key = standards_x_key
        self.standards_y_key = standards_y_key
        self.unknown_y_key = unknown_y_key
        self.min_r_squared = min_r_squared
        self.min_standards = min_standards
        self.scale = scale
        if solve_for not in ("x", "y"):
            raise ValueError("solve_for must be 'x' or 'y'")
        self.solve_for = solve_for

    def _series(self, inputs: dict[str, Any]) -> tuple[list[float], list[float]]:
        xs = [float(v) for v in inputs[self.standards_x_key]]
        ys = [float(v) for v in inputs[self.standards_y_key]]
        return xs, ys

    def validate(self, inputs: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        for key in (self.standards_x_key, self.standards_y_key):
            value = inputs.get(key)
            if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
                errors.append(f"'{key}' must be a list of readings")
        if errors:
            return errors

        try:
            xs, ys = self._series(inputs)
        except (TypeError, ValueError):
            return ["Calibration standards contain a non-numeric entry"]

        if len(xs) != len(ys):
            errors.append(
                f"'{self.standards_x_key}' has {len(xs)} entries but "
                f"'{self.standards_y_key}' has {len(ys)}"
            )
        if len(xs) < self.min_standards:
            errors.append(
                f"Only {len(xs)} standards recorded; this method needs at least "
                f"{self.min_standards}"
            )
        if len(set(xs)) == 1:
            errors.append("All standards have the same concentration; no line can be fitted")
        return errors

    def compute_expected(self, inputs: dict[str, Any]) -> float:
        xs, ys = self._series(inputs)
        fit = signatures.least_squares_fit(xs, ys)
        unknown_y = float(inputs[self.unknown_y_key])
        if self.solve_for == "x":
            return fit.solve_for_x(unknown_y) * self.scale
        return fit.predict(unknown_y) * self.scale

    def extra_detail(self, inputs: dict[str, Any]) -> dict[str, Any]:
        try:
            xs, ys = self._series(inputs)
            return {"fit": signatures.least_squares_fit(xs, ys).as_dict()}
        except (ValueError, TypeError, KeyError):
            return {}

    def data_quality_signature(self, inputs: dict[str, Any]) -> SignatureHit | None:
        """Whether the calibration itself can support reading off an unknown.

        Checked before expected-vs-reported: if the standards do not fit a
        line, or the unknown sits outside the calibrated range, the number
        derived from them is unusable no matter what the student reported.
        """
        xs, ys = self._series(inputs)

        hit = signatures.detect_poor_linear_fit(xs, ys, self.min_r_squared)
        if hit:
            return hit

        hit = signatures.detect_non_monotonic(ys, expect=_direction(xs, ys))
        if hit:
            return hit

        if self.solve_for == "x":
            try:
                unknown_x = self.compute_expected(inputs) / (self.scale or 1.0)
            except (ValueError, ZeroDivisionError, KeyError, TypeError):
                return None
            return signatures.detect_extrapolation(xs, unknown_x)

        return None

    def detect_signature(
        self, inputs: dict[str, Any], expected: float, reported: float
    ) -> SignatureHit | None:
        hit = signatures.detect_unit_scale_error(expected, reported, self.tolerance)
        if hit:
            return hit

        return signatures.detect_rounding_drift(expected, reported, self.tolerance)


def _direction(xs: Sequence[float], ys: Sequence[float]) -> str:
    """Direction the standards imply, so monotonicity is judged correctly."""
    try:
        fit = signatures.least_squares_fit(xs, ys)
    except ValueError:
        return "increasing"
    return "increasing" if fit.slope >= 0 else "decreasing"
