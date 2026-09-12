"""Unit tests for the four shared checker types.

These use arbitrary reference configurations, NOT BACHY105 values --
manual-sourced ground truth is Category 1's job, and this file must not
pretend to it. What is tested here is that each checker type behaves the
way its contract says: recomputes, compares within tolerance, and lets
data-quality problems override a numeric match.
"""

from __future__ import annotations

import math

import pytest

from backend.tier1_compute.shared import signatures
from backend.tier1_compute.shared import (
    CalibrationCurveChecker,
    DirectFormulaChecker,
    EndpointDetectionChecker,
    Outcome,
    RegressionSlopeChecker,
    Tolerance,
)
from backend.tier1_compute.shared.types import Action


def _normality(i: dict) -> float:
    return (i["n1"] * i["v1"]) / i["v2"]


@pytest.fixture
def direct() -> DirectFormulaChecker:
    return DirectFormulaChecker(
        formula=_normality,
        required_inputs=("n1", "v1", "v2"),
        tolerance=Tolerance(rel_tol=0.02),
        positive_inputs=("n1", "v1", "v2"),
        nonzero_inputs=("v2",),
        transposable_inputs=("v1", "v2"),
        label="reference",
    )


GOOD = {"n1": 0.1, "v1": 25.0, "v2": 20.0}  # -> 0.125


class TestTolerance:
    def test_requires_at_least_one_bound(self):
        with pytest.raises(ValueError):
            Tolerance()

    def test_rejects_negative_bounds(self):
        with pytest.raises(ValueError):
            Tolerance(abs_tol=-1)

    def test_absolute_band(self):
        tol = Tolerance(abs_tol=0.5)
        assert tol.matches(10.0, 10.4)
        assert not tol.matches(10.0, 10.6)

    def test_relative_band(self):
        tol = Tolerance(rel_tol=0.01)
        assert tol.matches(100.0, 100.9)
        assert not tol.matches(100.0, 102.0)

    def test_either_bound_suffices(self):
        tol = Tolerance(abs_tol=1.0, rel_tol=0.0001)
        assert tol.matches(1000.0, 1000.5)

    def test_zero_expected_needs_exact(self):
        assert Tolerance(rel_tol=0.1).matches(0.0, 0.0)
        assert not Tolerance(rel_tol=0.1).matches(0.0, 0.1)

    def test_non_finite_never_matches(self):
        tol = Tolerance(abs_tol=1.0)
        assert not tol.matches(math.nan, 1.0)
        assert not tol.matches(1.0, math.inf)


class TestDirectFormula:
    def test_pass(self, direct):
        result = direct.check(GOOD, 0.125)
        assert result.outcome is Outcome.PASS
        assert result.expected_value == pytest.approx(0.125)
        assert result.action() is Action.NONE

    def test_within_tolerance_still_passes(self, direct):
        assert direct.check(GOOD, 0.1262).outcome is Outcome.PASS

    def test_unit_scale_error(self, direct):
        result = direct.check(GOOD, 1.25)
        assert result.signature_code == "unit_scale_error"
        assert result.action() is Action.FIX_IN_PLACE

    def test_transposed_inputs(self, direct):
        result = direct.check(GOOD, 0.08)
        assert result.signature_code == "transposed_inputs"
        assert result.signature.evidence["swapped"] == ["v1", "v2"]

    def test_rounding_drift(self, direct):
        assert direct.check(GOOD, 0.13).signature_code == "rounding_drift"

    def test_unexplained_failure_has_no_signature(self, direct):
        result = direct.check(GOOD, 0.42)
        assert result.outcome is Outcome.FAIL_NO_SIGNATURE
        assert result.signature_code is None
        # No signature means Tier 2/3, never a guess.
        assert result.action() is Action.AWAIT_REVIEW

    def test_missing_input_is_invalid(self, direct):
        result = direct.check({"n1": 0.1, "v1": 25.0}, 0.125)
        assert result.outcome is Outcome.INVALID
        assert any("v2" in e for e in result.errors)

    def test_negative_input_is_invalid(self, direct):
        result = direct.check({"n1": 0.1, "v1": -25.0, "v2": 20.0}, 0.125)
        assert result.outcome is Outcome.INVALID
        assert any("negative" in e for e in result.errors)

    def test_zero_divisor_is_invalid(self, direct):
        result = direct.check({"n1": 0.1, "v1": 25.0, "v2": 0.0}, 0.125)
        assert result.outcome is Outcome.INVALID

    def test_missing_reported_value_is_invalid(self, direct):
        assert direct.check(GOOD, None).outcome is Outcome.INVALID

    def test_sign_flip_only_when_enabled(self):
        checker = DirectFormulaChecker(
            formula=lambda i: i["a"],
            required_inputs=("a",),
            tolerance=Tolerance(rel_tol=0.01),
            check_sign_flip=True,
        )
        assert checker.check({"a": 5.0}, -5.0).signature_code == "sign_flip"


class TestCalibrationCurve:
    @pytest.fixture
    def cal(self) -> CalibrationCurveChecker:
        return CalibrationCurveChecker(
            standards_x_key="conc",
            standards_y_key="absorbance",
            unknown_y_key="unknown_abs",
            tolerance=Tolerance(rel_tol=0.05),
            min_r_squared=0.99,
        )

    LINEAR = {
        "conc": [1, 2, 3, 4, 5],
        "absorbance": [0.1, 0.2, 0.3, 0.4, 0.5],
        "unknown_abs": 0.25,
    }

    def test_reads_unknown_off_the_fit(self, cal):
        result = cal.check(self.LINEAR, 2.5)
        assert result.outcome is Outcome.PASS
        assert result.detail["fit"]["r_squared"] == pytest.approx(1.0)

    def test_poor_fit_overrides_a_numeric_match(self, cal):
        """A bad calibration is the finding even if the number looks right."""
        noisy = {
            "conc": [1, 2, 3, 4, 5],
            "absorbance": [0.1, 0.5, 0.15, 0.9, 0.2],
            "unknown_abs": 0.25,
        }
        expected = cal.compute_expected(noisy)
        result = cal.check(noisy, expected)  # reported == recomputed
        assert result.outcome is Outcome.FAIL_WITH_SIGNATURE
        assert result.signature_code == "poor_linear_fit"
        assert result.detail["failed_on"] == "data_quality"

    def test_extrapolation_detected(self, cal):
        result = cal.check(
            {"conc": [1, 2, 3], "absorbance": [0.1, 0.2, 0.3], "unknown_abs": 0.9}, 9.0
        )
        assert result.signature_code == "extrapolated_beyond_standards"

    def test_too_few_standards_is_invalid(self, cal):
        result = cal.check(
            {"conc": [1, 2], "absorbance": [0.1, 0.2], "unknown_abs": 0.15}, 1.5
        )
        assert result.outcome is Outcome.INVALID

    def test_mismatched_series_lengths_is_invalid(self, cal):
        result = cal.check(
            {"conc": [1, 2, 3], "absorbance": [0.1, 0.2], "unknown_abs": 0.15}, 1.5
        )
        assert result.outcome is Outcome.INVALID

    def test_identical_standards_cannot_fit(self, cal):
        result = cal.check(
            {"conc": [2, 2, 2], "absorbance": [0.1, 0.2, 0.3], "unknown_abs": 0.15}, 2.0
        )
        assert result.outcome is Outcome.INVALID

    def test_non_list_series_is_invalid(self, cal):
        result = cal.check(
            {"conc": "1,2,3", "absorbance": [0.1, 0.2, 0.3], "unknown_abs": 0.15}, 1.5
        )
        assert result.outcome is Outcome.INVALID


class TestEndpointDetection:
    @pytest.fixture
    def peak(self) -> EndpointDetectionChecker:
        return EndpointDetectionChecker(
            x_key="volume",
            y_key="dEdV",
            geometry="peak",
            tolerance=Tolerance(abs_tol=0.2),
            min_points=5,
            max_increment=1.0,
            min_prominence=5.0,
        )

    @pytest.fixture
    def intersection(self) -> EndpointDetectionChecker:
        return EndpointDetectionChecker(
            x_key="volume",
            y_key="conductance",
            geometry="intersection",
            tolerance=Tolerance(abs_tol=0.3),
            min_points=6,
            min_span=1.0,
        )

    SHARP = {"volume": [8, 9, 10, 11, 12], "dEdV": [2, 5, 40, 6, 2]}
    VSHAPE = {
        "volume": [1, 2, 3, 4, 5, 6, 7, 8],
        "conductance": [10, 8, 6, 4, 6, 8, 10, 12],
    }

    def test_peak_endpoint(self, peak):
        assert peak.check(self.SHARP, 10.0).outcome is Outcome.PASS

    def test_peak_refined_by_interpolation(self, peak):
        """The endpoint is not quantised to a dosed volume."""
        asymmetric = {"volume": [8, 9, 10, 11, 12], "dEdV": [2, 5, 40, 20, 2]}
        endpoint = peak.find_endpoint(asymmetric)
        assert 10.0 < endpoint < 11.0

    def test_unresolved_peak_overrides_numeric_match(self, peak):
        broad = {"volume": [8, 8.5, 9, 9.5, 10], "dEdV": [2.0, 2.5, 3.0, 2.6, 2.1]}
        result = peak.check(broad, peak.find_endpoint(broad))
        assert result.signature_code == "unresolved_peak"

    def test_coarse_increments_override_numeric_match(self, peak):
        coarse = {"volume": [0, 5, 10, 15, 20], "dEdV": [2, 5, 40, 6, 2]}
        result = peak.check(coarse, peak.find_endpoint(coarse))
        assert result.signature_code == "coarse_increments"
        assert result.action().value == "redo_step"

    def test_intersection_endpoint_is_exact(self, intersection):
        assert intersection.find_endpoint(self.VSHAPE) == pytest.approx(4.0)

    def test_intersection_pass(self, intersection):
        assert intersection.check(self.VSHAPE, 4.0).outcome is Outcome.PASS

    def test_flat_response(self, intersection):
        flat = {"volume": [1, 2, 3, 4, 5, 6], "conductance": [5, 5, 5, 5, 5, 5]}
        result = intersection.check(flat, 3.0)
        assert result.signature_code == "flat_response"
        assert result.action().value == "restart"

    def test_derive_maps_endpoint_to_final_value(self):
        checker = EndpointDetectionChecker(
            x_key="volume",
            y_key="dEdV",
            geometry="peak",
            tolerance=Tolerance(rel_tol=0.01),
            derive=lambda endpoint, i: endpoint * i["factor"],
            extra_required=("factor",),
            min_points=5,
        )
        data = dict(self.SHARP, factor=2.0)
        assert checker.compute_expected(data) == pytest.approx(20.0, rel=1e-2)

    def test_unsorted_input_is_handled(self, intersection):
        shuffled = {
            "volume": [8, 1, 5, 2, 7, 3, 6, 4],
            "conductance": [12, 10, 6, 8, 10, 6, 8, 4],
        }
        assert intersection.find_endpoint(shuffled) == pytest.approx(4.0)

    def test_peak_at_edge_is_not_extrapolated(self, peak):
        """A maximum at the edge means the real peak is outside the window.

        Reporting the edge honestly is better than inventing a refinement
        from points that do not bracket a maximum.
        """
        rising = {"volume": [8, 9, 10, 11, 12], "dEdV": [2, 5, 10, 20, 40]}
        assert peak.find_endpoint(rising) == pytest.approx(12.0)

    def test_bad_geometry_rejected(self):
        with pytest.raises(ValueError):
            EndpointDetectionChecker(
                x_key="a", y_key="b", geometry="spiral", tolerance=Tolerance(abs_tol=1)
            )


class TestRegressionSlope:
    @pytest.fixture
    def kinetics(self) -> RegressionSlopeChecker:
        return RegressionSlopeChecker(
            x_key="t",
            y_key="conc",
            tolerance=Tolerance(rel_tol=0.05),
            min_r_squared=0.98,
            transform_y=math.log,
            slope_to_value=lambda s: -s,
            min_points=4,
            expect_direction="decreasing",
        )

    TIMES = [0, 10, 20, 30, 40, 50]
    CONC = [math.exp(-0.05 * t) for t in TIMES]

    def test_recovers_the_rate_constant(self, kinetics):
        result = kinetics.check({"t": self.TIMES, "conc": self.CONC}, 0.05)
        assert result.outcome is Outcome.PASS
        assert result.expected_value == pytest.approx(0.05, rel=1e-6)

    def test_sign_flip(self, kinetics):
        result = kinetics.check({"t": self.TIMES, "conc": self.CONC}, -0.05)
        assert result.signature_code == "sign_flip"

    def test_undefined_transform_is_invalid_not_a_diagnosis(self, kinetics):
        result = kinetics.check(
            {"t": self.TIMES, "conc": [1.0, 0.5, 0.0, -0.1, 0.2, 0.1]}, 0.05
        )
        assert result.outcome is Outcome.INVALID
        assert any("transform" in e for e in result.errors)

    def test_poor_fit_overrides_numeric_match(self, kinetics):
        scattered = {"t": self.TIMES, "conc": [1.0, 0.2, 0.9, 0.1, 0.8, 0.15]}
        expected = kinetics.compute_expected(scattered)
        result = kinetics.check(scattered, expected)
        assert result.signature_code == "poor_linear_fit"

    def test_too_few_points_is_invalid(self, kinetics):
        result = kinetics.check({"t": [0, 10], "conc": [1.0, 0.6]}, 0.05)
        assert result.outcome is Outcome.INVALID


class TestSignatureHelpers:
    """The shared detectors, exercised directly."""

    def test_least_squares_recovers_a_known_line(self):
        fit = signatures.least_squares_fit([0, 1, 2, 3], [1, 3, 5, 7])
        assert fit.slope == pytest.approx(2.0)
        assert fit.intercept == pytest.approx(1.0)
        assert fit.r_squared == pytest.approx(1.0)
        assert fit.predict(4) == pytest.approx(9.0)
        assert fit.solve_for_x(9.0) == pytest.approx(4.0)

    def test_least_squares_needs_variation_in_x(self):
        with pytest.raises(ValueError):
            signatures.least_squares_fit([2, 2, 2], [1, 2, 3])

    def test_least_squares_needs_two_points(self):
        with pytest.raises(ValueError):
            signatures.least_squares_fit([1], [1])

    def test_non_monotonic_reports_where_it_reversed(self):
        hit = signatures.detect_non_monotonic([1, 2, 5, 4, 6], expect="increasing")
        assert hit is not None
        assert hit.code == "non_monotonic_data"
        assert hit.evidence["reversal_indices"] == [3]

    def test_monotonic_series_produces_no_hit(self):
        assert signatures.detect_non_monotonic([1, 2, 3, 4], expect="increasing") is None

    def test_decreasing_direction_respected(self):
        assert signatures.detect_non_monotonic([4, 3, 2, 1], expect="decreasing") is None
        assert signatures.detect_non_monotonic([4, 5, 2, 1], expect="decreasing")

    def test_sign_flip_requires_matching_magnitude(self):
        """A wrong sign AND a wrong magnitude is not a polarity error."""
        tol = Tolerance(rel_tol=0.02)
        assert signatures.detect_sign_flip(5.0, -5.0, tol) is not None
        assert signatures.detect_sign_flip(5.0, -9.0, tol) is None

    def test_extrapolation_inside_range_is_clean(self):
        assert signatures.detect_extrapolation([1, 2, 3], 2.0) is None
        assert signatures.detect_extrapolation([1, 2, 3], 7.0) is not None


class TestNoLLMReachableFromTier1:
    """The hard rule in CLAUDE.md, enforced mechanically."""

    def test_tier1_package_never_imports_the_llm_layer(self):
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[1] / "tier1_compute"
        offenders = []
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for marker in ("backend.llm", "backend.rag", "get_backend", "httpx"):
                if marker in text:
                    offenders.append(f"{path.name}: {marker}")
        assert not offenders, (
            "Tier 1 must never reach an LLM or the network. Found: " + "; ".join(offenders)
        )
