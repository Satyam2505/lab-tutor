"""Experiment 07 -- computational method choice (ethane conformers).

STATUS: mechanism implemented; experiment identity pending manual check.

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

TODO (manual): confirm that experiment 7 in the BACHY105 manual is in
fact the ethane conformer calculation, and that the manual asks for the
comparison encoded below. The conformer ordering itself is standard
chemistry, but the experiment *numbering* and the exact labels students
are told to report must be verified against the manual before the pilot.
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
        manual_reference="TODO: confirm section/page against the BACHY105 manual",
        orderings=ORDERINGS,
        step_specs=STEPS,
    )
)
