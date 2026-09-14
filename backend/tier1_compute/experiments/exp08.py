"""Experiment 08 -- Conformational analysis of ethane AND cyclohexane.

STATUS: mechanism implemented, confirmed against IACHY102 manual p.43-47.

Corrected from the pre-manual guess: the earlier code split this across
exp07.py (ethane only) and exp08.py (cyclohexane only), as two separate
experiments. The real manual has ONE experiment -- "Conformational
analysis of cyclohexane and ethane molecules and plotting the potential
energy profile" -- covering both molecule pairs. See
`manual/IACHY102_manual.md` and `docs/final_audit.md`.

This verifies a *computational-method choice* (ORCA/orbital work), not a
measured quantity: there is no manual formula to recompute and no
expected-vs-measured comparison to make, so the ordinary Tier 1 path does
not apply. What is checked deterministically is the relative energy
ordering the chemistry requires. A contradiction is a determinate
finding; consistency is necessary but not sufficient (the method choice
itself still needs a human eye), so it escalates to Tier 3 rather than
being reported as a pass. An LLM may additionally read the student's
method narrative for a low-confidence, escalation-biased note (see
`backend/rag/qualitative.py`) -- this and Experiment 7's orbital-note path
(pending, see `exp07.py`) are the only places a model contributes to a
judgment at all; see CLAUDE.md's hard rule and its Exp 7/8 amendment.
"""

from __future__ import annotations

from backend.tier1_compute.experiments.registry import (
    QualitativeOrderingPlugin,
    register,
)
from backend.tier1_compute.shared.types import StepSpec

EXPERIMENT_ID = "exp08"

#: The first label must be LOWER in energy than the second. A pair is
#: skipped (not treated as an error) if the student did not report both
#: conformers in it -- e.g. twist-boat is optional.
ORDERINGS: tuple[tuple[str, str], ...] = (
    ("ethane_staggered", "ethane_eclipsed"),
    ("cyclohexane_chair", "cyclohexane_boat"),
    ("cyclohexane_chair", "cyclohexane_twist_boat"),
    ("cyclohexane_chair", "cyclohexane_half_chair"),
    ("cyclohexane_twist_boat", "cyclohexane_boat"),
    ("cyclohexane_twist_boat", "cyclohexane_half_chair"),
)

STEPS: tuple[StepSpec, ...] = (
    StepSpec(
        index=0,
        key="ethane_geometry_setup",
        prompt=(
            "Build both ethane conformers and report the H-C-C-H dihedral "
            "angle you used for each one."
        ),
        hints=(
            "Look again at how the two structures differ when you sight "
            "down the C-C bond.",
            "The two conformers are defined by the H-C-C-H dihedral angle. "
            "Check what value you set for each.",
            "One of your two geometries does not correspond to the "
            "conformer you have labelled it as -- re-check which dihedral "
            "belongs to which name before running the calculation.",
        ),
    ),
    StepSpec(
        index=1,
        key="ethane_energies",
        prompt="Report the converged energy you obtained for each ethane conformer.",
        hints=(
            "Check whether both calculations actually reached convergence.",
            "Compare the two energies against each other -- does their "
            "order match what you would predict from the geometries?",
            "Your reported ordering disagrees with the geometry you "
            "described; either the labels are swapped or one job did not "
            "converge.",
        ),
    ),
    StepSpec(
        index=2,
        key="cyclohexane_geometry_setup",
        prompt=(
            "Build each cyclohexane conformer you were asked to compare "
            "and describe how you constructed it."
        ),
        hints=(
            "Check that each ring you built is actually the conformer you "
            "have named.",
            "A boat and a twist-boat are easy to confuse during setup -- "
            "look at the relationship between the two out-of-plane "
            "carbons.",
            "At least one of your structures is not the conformer it is "
            "labelled as; rebuild it before running the calculation.",
        ),
    ),
    StepSpec(
        index=3,
        key="cyclohexane_energies",
        prompt="Report the optimised energy for each cyclohexane conformer.",
        hints=(
            "Check whether every optimisation converged before you read "
            "the energies off.",
            "Put your energies in order and compare that order against "
            "what ring strain would predict.",
            "The order you reported disagrees with the expected stability "
            "ordering -- check for swapped labels or an unconverged job.",
        ),
        is_final=True,
    ),
)

register(
    QualitativeOrderingPlugin(
        id=EXPERIMENT_ID,
        title="Conformational analysis of cyclohexane and ethane",
        manual_reference="IACHY102 manual, p.43-47",
        orderings=ORDERINGS,
        step_specs=STEPS,
    )
)
