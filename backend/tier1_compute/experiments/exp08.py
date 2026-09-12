"""Experiment 08 -- computational method choice (cyclohexane conformers).

STATUS: mechanism implemented and, per the Phase 1 IACHY102 audit, this
one has the RIGHT experiment id -- conformational analysis is confirmed
as experiment 8 (see `backend/scope/ontology.py` and
`docs/current_state_audit.md` §3.1). What is still pending is scope, not
numbering: the brief describes experiment 8 as covering *both* ethane
(staggered/eclipsed) *and* cyclohexane (chair/boat) conformers as one
experiment, while ethane's ordering check currently lives, mislabelled,
in `exp07.py`. See `docs/handoff_phase2.md` item 1 for the merge.

The second and last of the method-choice experiments. See `exp07.py` for
the full rationale; the same rules apply here. Chair cyclohexane must
come out lower in energy than the boat conformer. A contradiction is a
determinate finding; consistency escalates to Tier 3 rather than being
reported as a pass, because the method choice itself is what the
experiment is actually assessing.

TODO (manual): confirm the exact labels students are asked to report,
and merge in ethane's ordering pairs from `exp07.py` once that module's
tests are moved over.
"""

from __future__ import annotations

from backend.tier1_compute.experiments.registry import (
    QualitativeOrderingPlugin,
    register,
)
from backend.tier1_compute.shared.types import StepSpec

EXPERIMENT_ID = "exp08"

#: The first label must be LOWER in energy than the second. Twist-boat is
#: included only when the student reports it; a missing pair is skipped
#: rather than treated as an error.
ORDERINGS: tuple[tuple[str, str], ...] = (
    ("cyclohexane_chair", "cyclohexane_boat"),
    ("cyclohexane_chair", "cyclohexane_twist_boat"),
    ("cyclohexane_twist_boat", "cyclohexane_boat"),
)

STEPS: tuple[StepSpec, ...] = (
    StepSpec(
        index=0,
        key="geometry_setup",
        prompt=(
            "Build each cyclohexane conformer you were asked to compare and "
            "describe how you constructed it."
        ),
        hints=(
            "Check that each ring you built is actually the conformer you "
            "have named.",
            "A boat and a twist-boat are easy to confuse during setup -- "
            "look at the relationship between the two out-of-plane carbons.",
            "At least one of your structures is not the conformer it is "
            "labelled as; rebuild it before running the calculation.",
        ),
    ),
    StepSpec(
        index=1,
        key="optimised_energies",
        prompt="Report the optimised energy for each conformer.",
        hints=(
            "Check whether every optimisation converged before you read the "
            "energies off.",
            "Put your energies in order and compare that order against what "
            "ring strain would predict.",
            "The order you reported disagrees with the expected stability "
            "ordering -- check for swapped labels or an unconverged job.",
        ),
        is_final=True,
    ),
)

register(
    QualitativeOrderingPlugin(
        id=EXPERIMENT_ID,
        title="Conformational analysis of cyclohexane (computational)",
        manual_reference="TODO: confirm section/page against the IACHY102 manual",
        orderings=ORDERINGS,
        step_specs=STEPS,
    )
)
