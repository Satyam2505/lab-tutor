"""Checker type: regression-slope experiments.

Kinetics-style experiments where the answer is a rate constant read off
the slope of a transformed plot (ln[A] vs t for first order, 1/[A] vs t
for second order). The plugin supplies the transform and the slope ->
constant conversion from the manual; everything else is shared.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import Any

from backend.tier1_compute.shared.base import Checker
from backend.tier1_compute.shared import signatures
from backend.tier1_compute.shared.types import SignatureHit, Tolerance


class RegressionSlopeChecker(Checker):
    """Fit a slope to transformed data, convert it to the reported constant.

    Args:
        x_key / y_key: the raw independent and dependent series.
        transform_x / transform_y: per-point transforms from the manual
            (e.g. ``math.log`` for a first-order plot). Identity if None.
        slope_to_value: ``slope -> reported quantity`` (e.g. ``-slope``
            for a first-order rate constant). Identity if None.
        min_r_squared: fit-quality floor from the manual.
        min_points: minimum readings the method requires.
        expect_direction: ``"increasing"`` or ``"decreasing"`` for the
            raw response, used by the monotonicity detector. None
            disables that check.
    """

    def __init__(
        self,
        *,
        x_key: str,
        y_key: str,
        tolerance: Tolerance,
        min_r_squared: float,
        transform_x: Callable[[float], float] | None = None,
        transform_y: Callable[[float], float] | None = None,
        slope_to_value: Callable[[float], float] | None = None,
        min_points: int = 4,
        expect_direction: str | None = None,
        label: str = "",
    ) -> None:
        super().__init__(required_inputs=(x_key, y_key), tolerance=tolerance, label=label)
        self.x_key = x_key
        self.y_key = y_key
        self.min_r_squared = min_r_squared
        self.min_points = min_points
        self.expect_direction = expect_direction
        self._tx = transform_x
        self._ty = transform_y
        self._slope_to_value = slope_to_value

    def _raw(self, inputs: dict[str, Any]) -> tuple[list[float], list[float]]:
        return (
            [float(v) for v in inputs[self.x_key]],
            [float(v) for v in inputs[self.y_key]],
        )

    def _transformed(self, inputs: dict[str, Any]) -> tuple[list[float], list[float]]:
        xs, ys = self._raw(inputs)
        tx = [self._tx(v) for v in xs] if self._tx else xs
        ty = [self._ty(v) for v in ys] if self._ty else ys
        return tx, ty

    def validate(self, inputs: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        for key in (self.x_key, self.y_key):
            value = inputs.get(key)
            if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
                errors.append(f"'{key}' must be a list of readings")
        if errors:
            return errors

        try:
            xs, ys = self._raw(inputs)
        except (TypeError, ValueError):
            return ["Kinetics data contains a non-numeric entry"]

        if len(xs) != len(ys):
            errors.append(
                f"'{self.x_key}' has {len(xs)} entries but '{self.y_key}' has {len(ys)}"
            )
        if len(xs) < self.min_points:
            errors.append(
                f"Only {len(xs)} readings recorded; this method needs at least "
                f"{self.min_points}"
            )
        # A transform that is undefined on the data is a data problem, not
        # a diagnosis -- surface it before anything tries to fit a line.
        try:
            tx, ty = self._transformed(inputs)
        except (ValueError, ZeroDivisionError):
            errors.append(
                "The plotted transform is undefined for at least one reading "
                "(a zero or negative concentration cannot be logged or inverted)"
            )
            return errors
        if any(not math.isfinite(v) for v in tx + ty):
            errors.append("The plotted transform produced a non-finite value")
        return errors

    def compute_expected(self, inputs: dict[str, Any]) -> float:
        tx, ty = self._transformed(inputs)
        fit = signatures.least_squares_fit(tx, ty)
        if self._slope_to_value is None:
            return fit.slope
        return float(self._slope_to_value(fit.slope))

    def extra_detail(self, inputs: dict[str, Any]) -> dict[str, Any]:
        try:
            tx, ty = self._transformed(inputs)
            return {"fit": signatures.least_squares_fit(tx, ty).as_dict()}
        except (ValueError, KeyError, TypeError, ZeroDivisionError):
            return {}

    def data_quality_signature(self, inputs: dict[str, Any]) -> SignatureHit | None:
        """Whether a slope read off this data means anything.

        Checked before expected-vs-reported: a rate constant taken from
        points that do not fall on a line is not a measurement, even if
        the reported figure happens to be close.
        """
        tx, ty = self._transformed(inputs)

        hit = signatures.detect_insufficient_points(tx, self.min_points)
        if hit:
            return hit

        hit = signatures.detect_poor_linear_fit(tx, ty, self.min_r_squared)
        if hit:
            return hit

        if self.expect_direction:
            _, raw_y = self._raw(inputs)
            return signatures.detect_non_monotonic(raw_y, expect=self.expect_direction)

        return None

    def detect_signature(
        self, inputs: dict[str, Any], expected: float, reported: float
    ) -> SignatureHit | None:
        # A sign error on the slope->constant conversion is the single most
        # common mistake in this experiment shape.
        hit = signatures.detect_sign_flip(expected, reported, self.tolerance)
        if hit:
            return hit

        hit = signatures.detect_unit_scale_error(expected, reported, self.tolerance)
        if hit:
            return hit

        return signatures.detect_rounding_drift(expected, reported, self.tolerance)
