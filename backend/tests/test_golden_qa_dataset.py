"""The Q&A golden dataset, replayed against the live pipeline.

`golden_dataset/qa/generate_qa.py` verifies every case at generation
time and refuses to write the file if a case doesn't actually resolve
the way it claims. This test re-runs that same check on every commit,
against whatever the pipeline does *now* -- so a change to
`backend/scope/` or `backend/retrieval/` that quietly breaks one of
these 600+ real-shaped student questions is caught here rather than
discovered later. It intentionally does not re-import the generator's
templates; it treats each written case as a black-box fixture.
"""

from __future__ import annotations

import json

import pytest

from backend.retrieval.index import HybridIndex, get_index, reset_index_cache
from backend.retrieval.pipeline import answer_question
from backend.scope import ontology
from backend.scope.statuses import AnswerStatus
from backend.tests.conftest import GOLDEN

QA_DIR = GOLDEN / "qa"


def _case_files() -> list:
    if not QA_DIR.exists():
        return []
    return sorted(QA_DIR.glob("exp*.json"))


def _all_cases() -> list[dict]:
    cases = []
    for path in _case_files():
        payload = json.loads(path.read_text(encoding="utf-8"))
        for case in payload["cases"]:
            cases.append(case)
    return cases


ALL_CASES = _all_cases()


def test_qa_dataset_exists_and_meets_the_brief_minimum():
    assert QA_DIR.exists(), "golden_dataset/qa/ is missing; run generate_qa.py"
    assert len(ALL_CASES) >= 500, (
        f"only {len(ALL_CASES)} QA cases -- brief section 8 asks for a minimum of 500"
    )


def test_every_assessed_experiment_has_cases():
    covered = {c["experiment"] for c in ALL_CASES}
    assert covered == set(ontology.ALL_EXPERIMENT_IDS)


def test_priority_experiments_get_the_heaviest_coverage():
    counts: dict[str, int] = {}
    for c in ALL_CASES:
        counts[c["experiment"]] = counts.get(c["experiment"], 0) + 1
    assert counts["exp07"] >= 150, "experiment 7 is P0+ and must have the deepest coverage"
    for exp_id in ("exp02", "exp03", "exp08"):
        assert counts[exp_id] >= 100
    for exp_id in ontology.PRIORITY:
        if ontology.PRIORITY[exp_id] == "P1":
            assert counts[exp_id] >= 15


def test_every_case_declares_no_fabricated_answer_content():
    """The brief forbids inventing expected_answer_facts (section 8-9);
    the audit forbids it explicitly (section 0). Every case must say so."""
    for case in ALL_CASES:
        assert case["expected_answer_facts"] is None
        if not case.get("citation_expected", False):
            assert case.get("blocked_reason"), (
                f"{case['id']}: a non-answering case must record why"
            )


@pytest.fixture(scope="module")
def qa_index() -> HybridIndex:
    reset_index_cache()
    index = get_index()
    yield index
    reset_index_cache()


@pytest.mark.parametrize("case", ALL_CASES, ids=lambda c: c["id"])
async def test_case_replays_to_its_recorded_status(case, qa_index):
    """Ground truth here is 'what the live system does today', recorded at
    generation time -- this test asserts that hasn't silently drifted."""
    active = case["experiment"] if case["scope_label_intent"] != "out_of_scope" else None
    result = await answer_question(case["user_question"], active_experiment=active, index=qa_index, use_llm=False)
    assert result.status.value == case["expected_behavior"], (
        f"{case['id']} ({case['user_question']!r}): recorded "
        f"{case['expected_behavior']}, now resolves to {result.status.value}"
    )


def test_out_of_scope_cases_never_carry_a_citation_expectation():
    for c in ALL_CASES:
        if c["scope_label_intent"] == "out_of_scope":
            assert c["expected_behavior"] == AnswerStatus.OUT_OF_SCOPE.value
            assert not c["citation_expected"]


def test_adversarial_cases_never_resolve_out_of_scope():
    """An adversarial probe about a real experiment must be recognised as
    in-domain even while being refused its actual ask (the final answer)."""
    for c in ALL_CASES:
        if c["adversarial"]:
            assert c["expected_behavior"] != AnswerStatus.OUT_OF_SCOPE.value


def test_direct_and_messy_variants_of_the_same_experiment_route_consistently():
    """Hinglish/typo phrasing must not change which experiment a question
    belongs to -- spot-checked across the whole dataset rather than one
    hand-picked pair."""
    by_experiment: dict[str, set[str | None]] = {}
    for c in ALL_CASES:
        if c["scope_label_intent"] in ("direct_clean", "direct_messy"):
            by_experiment.setdefault(c["experiment"], set()).add(c["routed_experiment"])
    for experiment_id, routed_to in by_experiment.items():
        assert routed_to == {experiment_id}, (
            f"{experiment_id}: some direct-question cases routed elsewhere: {routed_to}"
        )
