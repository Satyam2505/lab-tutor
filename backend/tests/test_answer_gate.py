"""The answer gate's guarantee, tested structurally.

These tests are the ones that would fail if someone weakened the gate by
"just passing the expected value in so the model can phrase it better".
That change is exactly what the design forbids, and `assert_gate_invariant`
plus the field-set assertion below are what stop it reaching production.
"""

from __future__ import annotations

import dataclasses

import pytest

from backend.answer_gate import (
    PrematureRevealError,
    SocraticLLMInput,
    assert_gate_invariant,
    build_reveal,
    may_reveal,
    prepare_socratic_input,
    scrub_outbound,
)
from backend.answer_gate.gate import ALLOWED_SOCRATIC_FIELDS, FORBIDDEN_FIELD_HINTS


class TestPromptObjectCannotCarryTheAnswer:
    def test_field_set_is_exactly_the_allowed_set(self):
        actual = {f.name for f in dataclasses.fields(SocraticLLMInput)}
        assert actual == set(ALLOWED_SOCRATIC_FIELDS)

    def test_no_field_name_suggests_an_answer(self):
        for field in dataclasses.fields(SocraticLLMInput):
            lowered = field.name.lower()
            for bad in FORBIDDEN_FIELD_HINTS:
                assert bad not in lowered, (
                    f"field '{field.name}' looks like it could carry the answer"
                )

    def test_invariant_check_passes_as_shipped(self):
        assert_gate_invariant() is None

    def test_instance_is_frozen_and_slotted(self):
        """An answer cannot be attached after construction either."""
        gate_input = prepare_socratic_input(
            student_message="hi", step_prompt="Do step one.", step_index=0, total_steps=3
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            gate_input.hint_text = "0.125"  # type: ignore[misc]
        # Adding a brand-new attribute is refused too. The exact exception
        # type varies between Python versions for frozen+slots dataclasses,
        # so assert the refusal rather than the flavour of it.
        with pytest.raises((AttributeError, TypeError)):
            gate_input.expected_answer = 0.125  # type: ignore[attr-defined]
        assert not hasattr(gate_input, "expected_answer")

    def test_prepare_has_no_parameter_for_an_answer(self):
        import inspect

        params = set(inspect.signature(prepare_socratic_input).parameters)
        assert params == set(ALLOWED_SOCRATIC_FIELDS)

    def test_serialised_form_contains_only_allowed_fields(self):
        gate_input = prepare_socratic_input(
            student_message="what's the answer",
            step_prompt="Report the endpoint volume.",
            step_index=1,
            total_steps=3,
            hint_text="Look at where the lines cross.",
        )
        assert set(gate_input.as_prompt_fields()) == set(ALLOWED_SOCRATIC_FIELDS)


class TestRevealGate:
    def test_may_reveal_only_when_verification_complete(self):
        assert may_reveal(all_steps_complete=True) is True
        assert may_reveal(all_steps_complete=False) is False

    def test_build_reveal_refuses_before_completion(self):
        with pytest.raises(PrematureRevealError):
            build_reveal(all_steps_complete=False, computed_value=0.125)

    def test_build_reveal_after_completion(self):
        text = build_reveal(
            all_steps_complete=True,
            computed_value=0.125,
            label="normality of the unknown",
            units="N",
            student_value=0.124,
            tolerance_description="+/-2% relative",
        )
        assert "0.125" in text
        assert "0.124" in text
        assert "normality of the unknown" in text

    def test_reveal_is_not_produced_by_a_model(self, fake_llm):
        """The reveal path must not call the inference backend at all."""
        build_reveal(all_steps_complete=True, computed_value=42.0)
        assert fake_llm.calls == []


class TestOutboundScrub:
    STEP = "Report the endpoint volume from your plot."

    def test_novel_number_is_redacted_mid_session(self):
        decision = scrub_outbound(
            "Your endpoint should come out at 24.85 mL.",
            all_steps_complete=False,
            permitted_sources=(self.STEP,),
        )
        assert decision.redacted
        assert "24.85" not in decision.text
        assert "24.85" in decision.redacted_tokens

    def test_number_the_student_already_wrote_is_kept(self):
        decision = scrub_outbound(
            "You entered 24.85, so check that against your plot.",
            all_steps_complete=False,
            permitted_sources=("I got 24.85 for the endpoint",),
        )
        assert not decision.redacted
        assert "24.85" in decision.text

    def test_number_from_the_step_prompt_is_kept(self):
        decision = scrub_outbound(
            "Remember the tolerance is 0.05 here.",
            all_steps_complete=False,
            permitted_sources=("Report the endpoint to within 0.05 mL",),
        )
        assert not decision.redacted

    def test_step_navigation_numbers_survive(self):
        decision = scrub_outbound(
            "That is step 2 of 5, so move on to step 3.",
            all_steps_complete=False,
            permitted_sources=(),
        )
        assert not decision.redacted
        assert "step 2 of 5" in decision.text

    def test_scrub_is_a_noop_once_complete(self):
        text = "The final value is 0.125."
        decision = scrub_outbound(text, all_steps_complete=True)
        assert decision.text == text
        assert not decision.redacted

    def test_multiple_novel_numbers_all_redacted(self):
        decision = scrub_outbound(
            "Try 24.85 or possibly 25.10 instead.",
            all_steps_complete=False,
            permitted_sources=(),
        )
        assert len(decision.redacted_tokens) == 2

    @pytest.mark.parametrize(
        "text",
        [
            "The answer is 0.125.",
            "You should get approximately 1.2345e-3.",
            "It works out to 99.99 percent.",
        ],
    )
    def test_answer_shaped_replies_never_survive(self, text):
        decision = scrub_outbound(
            text, all_steps_complete=False, permitted_sources=("Do the calculation.",)
        )
        assert decision.redacted
