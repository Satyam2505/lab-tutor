"""Common `Checker` contract for every shared checker type.

A checker recomputes the expected result **from the student's own raw
data** using the manual's formula, compares it to what the student
reported, and -- on a mismatch -- runs that experiment's configured
signature detectors.

It never compares against a professor-held answer key: this build has no
per-student key upload, by design. "Correct" here means *self-consistent
with your own measurements under the manual's formula*, which is the only
question Tier 1 is asked to answer.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Any

from backend.tier1_compute.shared.types import (
    Outcome,
    SignatureHit,
    Tier1Result,
    Tolerance,
)


class Checker(ABC):
    """Base class. Subclasses supply `compute_expected` and detectors."""

    def __init__(
        self,
        *,
        required_inputs: tuple[str, ...],
        tolerance: Tolerance,
        label: str = "",
    ) -> None:
        self.required_inputs = required_inputs
        self.tolerance = tolerance
        self.label = label

    # -- subclass hooks ---------------------------------------------------

    @abstractmethod
    def compute_expected(self, inputs: dict[str, Any]) -> float:
        """The manual's formula applied to the student's own inputs."""

    def detect_signature(
        self, inputs: dict[str, Any], expected: float, reported: float
    ) -> SignatureHit | None:
        """Run this experiment's configured detectors. Default: none match."""
        return None

    def data_quality_signature(self, inputs: dict[str, Any]) -> SignatureHit | None:
        """Problems with the raw data itself, judged before any comparison.

        These are deliberately checked *before* expected-vs-reported,
        because they invalidate the result even when the reported number
        happens to land inside tolerance. A titration sampled too coarsely
        to resolve its endpoint has not produced a defensible answer, and
        a student who writes down a plausible value anyway should still be
        told the run needs repeating.
        """
        return None

    def validate(self, inputs: dict[str, Any]) -> list[str]:
        """Structural checks beyond required-key presence. Override freely."""
        return []

    # -- fixed pipeline ---------------------------------------------------

    def _missing(self, inputs: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        for key in self.required_inputs:
            if key not in inputs or inputs[key] is None:
                errors.append(f"Missing required input: '{key}'")
        return errors

    def check(self, inputs: dict[str, Any], reported: float | None) -> Tier1Result:
        errors = self._missing(inputs)
        if not errors:
            errors.extend(self.validate(inputs))

        if reported is None:
            errors.append("No reported result to check")

        if errors:
            return Tier1Result(outcome=Outcome.INVALID, errors=errors)

        try:
            expected = float(self.compute_expected(inputs))
        except ZeroDivisionError:
            return Tier1Result(
                outcome=Outcome.INVALID,
                errors=["Recomputation divided by zero -- check for a zero input"],
            )
        except (ValueError, TypeError, KeyError) as exc:
            return Tier1Result(
                outcome=Outcome.INVALID, errors=[f"Could not recompute: {exc}"]
            )

        if not math.isfinite(expected):
            return Tier1Result(
                outcome=Outcome.INVALID,
                errors=["Recomputation did not produce a finite value"],
            )

        reported_f = float(reported)
        detail: dict[str, Any] = {
            "checker": type(self).__name__,
            "label": self.label,
            "tolerance": self.tolerance.describe(),
        }
        detail.update(self.extra_detail(inputs))

        # Data quality is judged first and overrides a numeric match --
        # see `data_quality_signature`.
        quality = self.data_quality_signature(inputs)
        if quality is not None:
            return Tier1Result(
                outcome=Outcome.FAIL_WITH_SIGNATURE,
                expected_value=expected,
                reported_value=reported_f,
                signature=quality,
                detail=detail | {"failed_on": "data_quality"},
            )

        if self.tolerance.matches(expected, reported_f):
            return Tier1Result(
                outcome=Outcome.PASS,
                expected_value=expected,
                reported_value=reported_f,
                detail=detail,
            )

        signature = self.detect_signature(inputs, expected, reported_f)
        return Tier1Result(
            outcome=(
                Outcome.FAIL_WITH_SIGNATURE if signature else Outcome.FAIL_NO_SIGNATURE
            ),
            expected_value=expected,
            reported_value=reported_f,
            signature=signature,
            detail=detail,
        )

    def extra_detail(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Structured facts worth attaching to the result (fit stats etc.)."""
        return {}
