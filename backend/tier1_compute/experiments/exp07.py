"""Experiment 07 -- Build atoms/molecules; orbital visualization; orbital
contributions (Gabedit -> ORCA -> Avogadro; CH4 and O2).

STATUS: NOT IMPLEMENTED. Registered as PendingManualPlugin so any attempt
to use it raises rather than silently reusing the wrong logic.

Corrected from the pre-manual guess: the earlier code registered exp07 as
a `QualitativeOrderingPlugin` checking ethane_staggered < ethane_eclipsed.
That is Experiment 8's content (see `exp08.py`), not Experiment 7's. The
real Experiment 7 (IACHY102 manual, p.39-42) is a DFT/orbital-contribution
workflow with no ordering to check at all: it asks the student to run six
method/basis-set combinations (B3LYP and B3P, each with 6-31G/6-31G*/
6-31G**) for CH4 and O2, and report HOMO/LUMO orbital energies (eV) plus
the s/p/d/f electron-count contribution per atom.

None of the four shared checker types fit this shape -- there is no
manual formula to recompute and no measured-vs-expected comparison, and
unlike Experiment 8 there is also no ordering between two conformers to
check (a single molecule at a single level of theory has one HOMO, one
LUMO). What a Tier 1 checker *could* verify deterministically, once
designed: job-completion/convergence markers in the ORCA output, and
physics-consistency facts that always hold regardless of the manual's
specific numbers (LUMO energy > HOMO energy for the same run; energy
after geometry optimization <= the initial single-point energy). That is
a fifth shared-checker shape ("computation sanity/convergence checker")
that does not exist yet in `backend/tier1_compute/shared/` -- do not
force this into `QualitativeOrderingPlugin` or `DirectFormulaChecker` to
make it "ready"; build the new checker type first. See
`docs/final_audit.md`.
"""

from __future__ import annotations

from backend.tier1_compute.experiments.registry import PendingManualPlugin, register

EXPERIMENT_ID = "exp07"

register(
    PendingManualPlugin(
        id=EXPERIMENT_ID,
        title="Build atoms and molecules; orbital contributions (Gabedit/ORCA/Avogadro)",
        manual_reference="IACHY102 manual, p.39-42",
        reason=(
            "No shared checker type covers a single-run orbital-energy "
            "report (no recompute-and-compare formula, no ordering "
            "between two values). Needs a new 'computation sanity' "
            "checker type (job-completion + HOMO<LUMO + energy-decreased-"
            "after-optimization) before this can be enabled; see the "
            "module docstring."
        ),
    )
)
