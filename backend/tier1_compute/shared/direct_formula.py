"""Checker type: direct-formula experiments.

One formula from the manual applied to the student's inputs, compared to
their reported value within the manual's stated tolerance. The most
common shape in BACHY105 -- titre-volume/normality calculations,
molecular-weight determinations, and similar single-expression results.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from backend.tier1_compute.shared.base import Checker
from backend.tier1_compute.shared import signatures
from backend.tier1_compute.shared.types import SignatureHit, Tolerance


class DirectFormulaChecker(Checker):
    """Config-only checker: a plugin supplies the formula and tolerance.

    Args:
        formula: pure function of the student's inputs. Must be the
            manual's expression, transcribed exactly.
        required_inputs: keys `formula` reads.
        tolerance: the manual's acceptance band.
        positive_inputs: keys that are physically non-negative, so a
            negative value is a validation error rather than a diagnosis.
        transposable_inputs: keys worth testing for label swaps. Leave
            empty to disable the transposition detector.
        check_sign_flip / check_unit_scale / check_rounding: enable the
            corresponding shared detector.
    """

    def __init__(
        self,
        *,
        formula: Callable[[dict[str, Any]], float],
        required_inputs: tuple[str, ...],
        tolerance: Tolerance,
        label: str = "",
        positive_inputs: Sequence[str] = (),
        nonzero_inputs: Sequence[str] = (),
        transposable_inputs: Sequence[str] = (),
        check_sign_flip: bool = False,
        check_unit_scale: bool = True,
        check_rounding: bool = True,
    ) -> None:
        super().__init__(
            required_inputs=required_inputs, tolerance=tolerance, label=label
        )
        self._formula = formula
        self._positive = tuple(positive_inputs)
        self._nonzero = tuple(nonzero_inputs)
        self._transposable = tuple(transposable_inputs)
        self._check_sign_flip = check_sign_flip
        self._check_unit_scale = check_unit_scale
        self._check_rounding = check_rounding

    def compute_expected(self, inputs: dict[str, Any]) -> float:
        return float(self._formula(inputs))

    def validate(self, inputs: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        for key in self._positive:
            value = inputs.get(key)
            if isinstance(value, (int, float)) and value < 0:
                errors.append(
                    f"'{key}' is {value:g}; this quantity cannot be negative"
                )
        for key in self._nonzero:
            value = inputs.get(key)
            if isinstance(value, (int, float)) and value == 0:
                errors.append(f"'{key}' is zero, which makes the result undefined")
        return errors

    def detect_signature(
        self, inputs: dict[str, Any], expected: float, reported: float
    ) -> SignatureHit | None:
        # Order matters: the most specific, most confidently-attributable
        # explanations are tested first.
        if self._check_sign_flip:
            hit = signatures.detect_sign_flip(expected, reported, self.tolerance)
            if hit:
                return hit

        if self._transposable:
            hit = signatures.detect_transposed_inputs(
                self._formula,
                inputs,
                reported,
                self.tolerance,
                candidate_keys=self._transposable,
            )
            if hit:
                return hit

        if self._check_unit_scale:
            hit = signatures.detect_unit_scale_error(expected, reported, self.tolerance)
            if hit:
                return hit

        if self._check_rounding:
            hit = signatures.detect_rounding_drift(expected, reported, self.tolerance)
            if hit:
                return hit

        return None
