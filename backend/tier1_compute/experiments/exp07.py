"""Experiment 07 -- registered here as ethane conformers. THIS IS WRONG.

STATUS: identity conflict CONFIRMED, not merely pending, as of the
Phase 1 IACHY102 audit (see `docs/current_state_audit.md` §3.1 and
`docs/handoff_phase2.md` item 1 for the exact fix). This module was
written before the current manual's topic list was available, on the
(reasonable at the time) guess that experiment 7 was a conformer
comparison. It is not.

Per the Phase 1 brief's own experiment descriptions -- confirmed
independently in `backend/scope/ontology.py`, which is sourced from the
same brief -- **experiment 7 is the molecular-orbital workflow**
(Gabedit / ORCA / Avogadro, methane and O2, geometry optimisation,
HOMO/LUMO, orbital contributions). **Experiment 8 covers both ethane
*and* cyclohexane conformers** as one experiment.

This file has NOT been renumbered in place. The ordering-check mechanism
below (staggered-vs-eclipsed) is real, tested, working Tier 1 logic --
it is simply attached to the wrong experiment id, and moving it touches
four test files with real DB fixtures (`test_pipeline_and_tiers.py`,
`test_phrasing_injection.py`, `test_data_isolation.py`,
`test_single_fire_and_summaries.py`). Rather than rewrite those under
time pressure without the manual in hand to double check the exact
labels students report, the swap is left as a scoped, mechanical Phase 2
task. Until then:

* `backend/scope/*` (the retrieval/Q&A router) uses the CORRECT
  identity: it will route a real experiment-7 question (HOMO/LUMO,
  orbital contribution) to `exp07` for retrieval purposes.
* `backend/tier1_compute/experiments/exp07.py` (this file, the
  diagnosis/grading pipeline) still runs the ethane-conformer check
  under the `exp07` id.
* These two subsystems therefore currently disagree about what `exp07`
  means. Do not assume they are consistent; check which one you are
  reading.

The chemistry-checking mechanism itself was originally documented as
follows and remains accurate for *whichever* experiment ends up wired
to it:

This is one of the two experiments that verify a *computational method
choice* (ORCA / orbital calculations) rather than a measured quantity.
There is no manual formula to recompute and no measured-vs-expected
comparison to make, so the ordinary Tier 1 path does not apply.

What is checked deterministically: the relative ordering the chemistry
requires. Staggered ethane must come out lower in energy than eclipsed
ethane. If the student's reported numbers contradict that, the finding is
determinate and needs no model. If they are consistent, that is
necessary but not sufficient -- the method choice itself still needs a
human eye -- so the result escalates to Tier 3 rather than being reported
as a pass.

An LLM may additionally read the student's method narrative, but only to
produce a low-confidence, escalation-biased note (see
`backend/rag/qualitative.py`). This and `exp08` are the only places in
the system where a model contributes to a judgment at all.
"""

from __future__ import annotations

from backend.tier1_compute.experiments.registry import (
    QualitativeOrderingPlugin,
    register,
)
from backend.tier1_compute.shared.types import StepSpec

EXPERIMENT_ID = "exp07"

#: Reported-energy keys and the ordering that must hold between them.
#: Read as: the first label must be LOWER in energy than the second.
ORDERINGS: tuple[tuple[str, str], ...] = (
    ("ethane_staggered", "ethane_eclipsed"),
)

STEPS: tuple[StepSpec, ...] = (
    StepSpec(
        index=0,
        key="geometry_setup",
        prompt=(
            "Build both ethane conformers and report the dihedral angle you "
            "used for each one."
        ),
        hints=(
            "Look again at how the two structures differ when you sight down "
            "the C-C bond.",
            "The two conformers are defined by the H-C-C-H dihedral angle. "
            "Check what value you set for each.",
            "One of your two geometries does not correspond to the conformer "
            "you have labelled it as -- re-check which dihedral belongs to "
            "which name before running the calculation.",
        ),
    ),
    StepSpec(
        index=1,
        key="single_point_energies",
        prompt="Report the converged energy you obtained for each conformer.",
        hints=(
            "Check whether both calculations actually reached convergence.",
            "Compare the two energies against each other -- does their order "
            "match what you would predict from the geometries?",
            "Your reported ordering disagrees with the geometry you described; "
            "either the labels are swapped or one job did not converge.",
        ),
        is_final=True,
    ),
)

register(
    QualitativeOrderingPlugin(
        id=EXPERIMENT_ID,
        title="Conformational energies of ethane (computational)",
        manual_reference="TODO: confirm section/page against the IACHY102 manual",
        orderings=ORDERINGS,
        step_specs=STEPS,
    )
)
