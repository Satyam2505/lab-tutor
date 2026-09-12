"""Experiment 09 -- Tier 1 plugin.

STATUS: pending manual transcription.

The BACHY105 manual PDF is not present in the repository, so this
experiment's formula, tolerance, expected data shape and Socratic steps
are unknown. Registering a `PendingManualPlugin` makes any attempt to use
it raise `ManualNotTranscribedError` instead of quietly producing a
diagnosis from invented chemistry.

To complete this file:

1. Read the experiment in the manual. Record the section/page in
   `manual_reference` so the transcription can be audited later.
2. Replace the registration below with a `DeterministicPlugin` wired to
   whichever shared checker type matches the experiment's shape:
       direct_formula      -- one formula, one comparison
       calibration_curve   -- fit standards, read off an unknown
       endpoint_detection  -- peak or line-intersection endpoint
       regression_slope    -- rate constant from a fitted slope
   Do NOT write bespoke math here; if none of the four fits, add a fifth
   shared checker type instead (see AGENTS.md, `tier1-compute-builder`).
3. Take the tolerance from the manual's own stated acceptance band. Do
   not invent one, and do not widen one to make a test pass.
4. Add the ordered `StepSpec`s for Socratic mode, each with its
   three-rung hint ladder. No rung may contain the numeric answer --
   `tests/test_socratic_refusal.py` asserts this structurally.
5. Add the manual's worked example to `golden_dataset/category1_worked_examples/`
   verbatim, and a test that this plugin reproduces it.

A worked reference implementation of all of the above lives in
`_template.py`.
"""

from __future__ import annotations

from backend.tier1_compute.experiments.registry import PendingManualPlugin, register

EXPERIMENT_ID = "exp09"

register(
    PendingManualPlugin(
        id=EXPERIMENT_ID,
        title="Experiment 9 (title pending manual transcription)",
        manual_reference="",
        reason=(
            "BACHY105 manual not present in the repository; formula, "
            "tolerance and Socratic steps have not been transcribed"
        ),
    )
)
