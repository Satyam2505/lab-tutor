"""Categories 1, 2 and 3 of the golden dataset, driven from their files."""

from __future__ import annotations

import json
import pathlib

import pytest

from backend.extraction import ExtractionError, extract_submission, parse_series
from backend.tests.conftest import GOLDEN, load_golden
from backend.tier1_compute.shared.types import Outcome

# ---------------------------------------------------------------------------
# Category 1 -- worked examples from the manual
# ---------------------------------------------------------------------------

CATEGORY1_DIR = GOLDEN / "category1_worked_examples"


def _category1_files() -> list[pathlib.Path]:
    if not CATEGORY1_DIR.exists():
        return []
    return sorted(CATEGORY1_DIR.glob("exp*.json"))


def test_category1_is_either_populated_or_explicitly_blocked():
    """Never silently absent.

    While the manual is missing this skips with a message naming why. It
    must not quietly pass, and it must not be satisfied by invented data.
    """
    files = _category1_files()
    if not files:
        readme = CATEGORY1_DIR / "README.md"
        assert readme.exists(), (
            "Category 1 has no data and no README explaining why. One or the "
            "other must be true."
        )
        pytest.skip(
            "Category 1 is empty: the IACHY102 manual is not in the repository, "
            "so there are no worked examples to transcribe. See "
            "golden_dataset/category1_worked_examples/README.md"
        )


@pytest.mark.parametrize(
    "path", _category1_files(), ids=lambda p: p.stem if hasattr(p, "stem") else str(p)
)
def test_category1_worked_example_reproduced(path):
    """Once populated, every worked example must be reproduced exactly."""
    from backend.tier1_compute.experiments import get_plugin

    payload = json.loads(path.read_text(encoding="utf-8"))
    experiment_id = payload["experiment_id"]
    assert payload.get("manual_reference"), (
        f"{path.name}: manual_reference is required so the transcription can "
        "be audited"
    )

    plugin = get_plugin(experiment_id)
    examples = payload.get("examples") or (
        [payload] if "expected_output" in payload else []
    )
    if not examples:
        pytest.skip(f"{experiment_id}: the manual gives no worked example")

    for example in examples:
        expected = example.get("expected_output", example.get("expected_value"))
        computed = plugin.compute_expected(example["inputs"])
        assert computed == pytest.approx(expected, rel=1e-3), (
            f"{path.name}: plugin computed {computed}, manual states {expected}"
        )


# ---------------------------------------------------------------------------
# Category 2 -- known deviations, one per signature rule
# ---------------------------------------------------------------------------


def _category2_cases() -> list[dict]:
    return load_golden("category2_known_deviations", "cases.json")["cases"]


@pytest.mark.parametrize("case", _category2_cases(), ids=lambda c: c["id"])
def test_category2_case_triggers_its_intended_rule(case):
    """A case that does not trigger its own rule is a bug, not a skip."""
    from golden_dataset.generate import CHECKERS

    checker = CHECKERS[case["checker"]]
    result = checker.check(case["inputs"], case["reported"])

    if case["signature"] == "insufficient_points":
        assert result.outcome is Outcome.INVALID
        assert any("at least" in e for e in result.errors)
        return

    assert result.outcome is Outcome.FAIL_WITH_SIGNATURE, (
        f"{case['id']}: expected a signature, got {result.outcome.value}"
    )
    assert result.signature_code == case["signature"]


def test_category2_covers_every_documented_signature():
    """Guards against a rule being added with no case to exercise it."""
    from backend.tier1_compute.shared.types import _SIGNATURE_ACTIONS

    covered = {c["signature"] for c in _category2_cases()}
    # Signatures that are unreachable through the reference configurations
    # used by the dataset, each for a stated reason.
    known_uncovered = {
        "arithmetic_slip",  # no detector implemented; reserved code
        "used_wrong_formula_branch",  # needs a real multi-branch manual formula
        "standards_not_bracketing",  # reserved; superseded by extrapolation
        "no_detectable_endpoint",  # covered in test_tier1_checkers, not by data
        "endpoint_outside_data_range",  # ditto
        "conformer_ordering_violated",  # exercised in the exp08 tests
        "energy_increased_after_optimization",  # exercised in the exp07 tests
        "homo_lumo_order_violated",  # exercised in the exp07 tests
    }
    missing = set(_SIGNATURE_ACTIONS) - covered - known_uncovered
    assert not missing, f"signatures with no Category 2 case: {sorted(missing)}"


def test_category2_cases_were_verified_at_generation_time():
    for case in _category2_cases():
        assert case.get("verified") is True, f"{case['id']} was written unverified"


# ---------------------------------------------------------------------------
# Category 3 -- adversarial and edge inputs
# ---------------------------------------------------------------------------


def _category3_cases() -> list[dict]:
    return load_golden("category3_edge_inputs", "cases.json")["cases"]


@pytest.mark.parametrize("case", _category3_cases(), ids=lambda c: c["id"])
def test_category3_edge_input(case):
    expect = case["expect"]

    if expect == "idempotent_replay":
        pytest.skip("Covered end-to-end in test_data_isolation.py::test_double_submit")

    if expect == "valid_extraction_invalid_tier1":
        # Extraction accepts the shape; Tier 1's own validation rejects it.
        from backend.tests.reference_plugin import FINAL_CHECKER

        result = FINAL_CHECKER.check(
            {
                "standard_normality": case["payload"]["n1"],
                "standard_volume": case["payload"]["v1"],
                "titre_volume": case["payload"]["v2"],
            },
            0.125,
        )
        assert result.outcome is Outcome.INVALID
        needle = case["expect_error_contains"]
        assert any(needle in e for e in result.errors), (
            f"{case['id']}: expected an error containing {needle!r}, "
            f"got {result.errors}"
        )
        return

    # Series-only cases exercise parse_series directly so a length rule can
    # be asserted without inventing an experiment.
    if case.get("series_fields") and expect == "invalid" and not case["payload"].get(
        list(case["payload"])[0]
    ):
        field = case["series_fields"][0]
        with pytest.raises(ExtractionError) as excinfo:
            parse_series(case["payload"][field], field, min_length=5)
        assert case["expect_error_contains"] in str(excinfo.value)
        return

    result = extract_submission(
        case["payload"],
        numeric_fields=tuple(case.get("numeric_fields", ())),
        series_fields=tuple(case.get("series_fields", ())),
        required=tuple(case.get("required", ())),
    )

    if expect == "valid":
        assert result.ok, f"{case['id']}: unexpected errors {result.errors}"
        for key, value in case.get("expect_value", {}).items():
            assert result.values[key] == pytest.approx(value)
    else:
        assert not result.ok, f"{case['id']}: expected rejection, got {result.values}"
        needle = case["expect_error_contains"]
        assert any(needle in e for e in result.errors), (
            f"{case['id']}: expected an error containing {needle!r}, "
            f"got {result.errors}"
        )


def test_no_edge_case_ever_produces_a_silent_guess():
    """Ambiguous input must never be resolved into a number."""
    for raw in ("12,34", "1.2.3", "1,234.5", "twenty five", "NaN", "Infinity"):
        result = extract_submission({"v": raw}, numeric_fields=("v",))
        assert not result.ok, f"{raw!r} was silently accepted as {result.values}"
        assert "v" not in result.values
