"""Experiment 09 -- Colorimetric estimation of Fe2+ (conventional and smartphone RGB).

STATUS: pending implementation (formula/shape known; no worked example to
verify against). See `manual/IACHY102_manual.md` for the full transcription
and `docs/final_audit.md` for the audit finding this comes from.

The IACHY102 manual is now in the repository (as a text transcription --
see manual/README.md), so the earlier "manual not present" reason no
longer applies. Formula is known (Beer's law calibration_curve against 1/2/3/4 ppm standards, lambda_max 510 nm, 1,10-phenanthroline complex; RGB-ratio variant) but the manual prints no worked numeric example (Table 1, p.51, is blank), so there is no manual-verified number to pin a Category 1 test against yet.

To complete this file:

1. Wire a `DeterministicPlugin` to the shared checker type named above.
   Do NOT write bespoke math here; if it genuinely does not fit, add a
   fifth shared checker type instead (see AGENTS.md, `tier1-compute-builder`).
2. Choose the tolerance deliberately and document why in a comment --
   the manual gives no experiment-specific numeric acceptance band beyond
   the course-wide marking rubric (p.8), which is a marks-vs-skill-value
   scale, not a Tier 1 self-consistency tolerance. Do not conflate them.
3. Add the ordered `StepSpec`s for Socratic mode, each with its
   three-rung hint ladder. No rung may contain the numeric answer --
   `tests/test_socratic_refusal.py` asserts this structurally.
4. If a worked example ever surfaces (an assignment key, a solved past
   paper, etc.), add it to `golden_dataset/category1_worked_examples/`
   verbatim and a test that this plugin reproduces it. Until then, this
   experiment's Category 1 coverage stays absent -- do not fabricate one.

A worked reference implementation of all of the above lives in
`_template.py`; `exp01.py` is a complete real example.
"""

from __future__ import annotations

from backend.tier1_compute.experiments.registry import PendingManualPlugin, register

EXPERIMENT_ID = "exp09"

register(
    PendingManualPlugin(
        id=EXPERIMENT_ID,
        title="Colorimetric estimation of Fe2+ (conventional and smartphone RGB)",
        manual_reference="IACHY102 manual, p.48-51",
        reason=(
            "Formula is known (Beer's law calibration_curve against 1/2/3/4 ppm standards, lambda_max 510 nm, 1,10-phenanthroline complex; RGB-ratio variant) but the manual prints no worked numeric example (Table 1, p.51, is blank), so there is no manual-verified number to pin a Category 1 test against yet."
        ),
    )
)
