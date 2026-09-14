"""Experiment 04 -- Analysis of iron in carbon steel by potentiometry.

STATUS: pending implementation (formula/shape known; no worked example to
verify against). See `manual/IACHY102_manual.md` for the full transcription
and `docs/final_audit.md` for the audit finding this comes from.

The IACHY102 manual is now in the repository (as a text transcription --
see manual/README.md), so the earlier "manual not present" reason no
longer applies. Formula is known (endpoint from an EMF-vs-volume S-curve or its ΔE/ΔV peak, then N(steel) = 0.05N * V_endpoint / 20mL) but the manual prints no worked numeric example (both titration tables, p.30-32, are blank), so there is no manual-verified number to pin a Category 1 test against yet.

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

EXPERIMENT_ID = "exp04"

register(
    PendingManualPlugin(
        id=EXPERIMENT_ID,
        title="Analysis of iron in carbon steel by potentiometry",
        manual_reference="IACHY102 manual, p.28-32",
        reason=(
            "Formula is known (endpoint from an EMF-vs-volume S-curve or its ΔE/ΔV peak, then N(steel) = 0.05N * V_endpoint / 20mL) but the manual prints no worked numeric example (both titration tables, p.30-32, are blank), so there is no manual-verified number to pin a Category 1 test against yet."
        ),
    )
)
