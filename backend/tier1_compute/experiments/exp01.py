"""Experiment 01 -- Thermodynamic functions from EMF measurements: Zn-Cu system.

STATUS: implemented from the IACHY102 manual (p.10-15). See
`manual/IACHY102_manual.md` for the full transcription and
`golden_dataset/category1_worked_examples/exp01.json` for the manual's
own worked numeric example, reproduced verbatim as a regression test.

Two quantities are checked, both recomputed from the student's own data:

1. Ecell via the Nernst equation, from the concentrations they used and
   the temperature they measured at (Socratic step 0 -- an intermediate
   quantity, never revealed as the final answer).
2. Delta-G = -nFEcell, from the student's own measured/computed Ecell
   (the final result the marks table asks for).

n=2 and Ecell(standard)=1.10 V are fixed properties of this cell (Zn/Cu,
a 2-electron transfer; Ecell(standard) = 0.340 - (-0.760), p.10-11) --
not per-run student inputs, so they are constants in the formula rather
than required keys.

Delta-H and Delta-S (p.14-15) also have a worked example, but the
manual's method pools Delta-G at two *different* temperatures from two
*different* runs before differencing -- a shape none of the four shared
checker types cover (they all check one run's own internal
consistency). Left unimplemented rather than forced into the wrong
shape; see docs/final_audit.md.
"""

from __future__ import annotations

import math
from typing import Any

from backend.tier1_compute.experiments.registry import DeterministicPlugin, register
from backend.tier1_compute.shared import DirectFormulaChecker, StepSpec, Tolerance

EXPERIMENT_ID = "exp01"

_R = 8.314  # J K^-1 mol^-1
_F = 96500.0  # C mol^-1
_N_ELECTRONS = 2  # Zn -> Zn2+ + 2e- / Cu2+ + 2e- -> Cu
_ECELL_STANDARD = 1.10  # V, p.10-11: 0.340 - (-0.760)


def _ecell_nernst(i: dict[str, Any]) -> float:
    """Ecell = Ecell(standard) - (RT/nF) * ln([Zn2+]/[Cu2+])  -- p.13."""
    return _ECELL_STANDARD - (_R * i["temperature_k"]) / (
        _N_ELECTRONS * _F
    ) * math.log(i["zn_conc"] / i["cu_conc"])


def _delta_g_kj(i: dict[str, Any]) -> float:
    """Delta-G (kJ/mol) = -n F Ecell  -- p.13."""
    return -(_N_ELECTRONS * _F * i["ecell"]) / 1000.0


ECELL_CHECKER = DirectFormulaChecker(
    formula=_ecell_nernst,
    required_inputs=("zn_conc", "cu_conc", "temperature_k"),
    tolerance=Tolerance(abs_tol=0.005),
    positive_inputs=("zn_conc", "cu_conc", "temperature_k"),
    nonzero_inputs=("cu_conc",),
    transposable_inputs=("zn_conc", "cu_conc"),
    check_unit_scale=True,
    check_rounding=True,
    label="Ecell (Nernst equation)",
)

DELTA_G_CHECKER = DirectFormulaChecker(
    formula=_delta_g_kj,
    required_inputs=("ecell",),
    tolerance=Tolerance(rel_tol=0.01),
    check_unit_scale=True,
    check_rounding=True,
    label="Delta-G from Ecell",
)

STEPS: tuple[StepSpec, ...] = (
    StepSpec(
        index=0,
        key="ecell_measurement",
        prompt=(
            "Report the Zn2+ and Cu2+ concentrations you used, the "
            "temperature, and the Ecell you measured for that pair."
        ),
        requires=("zn_conc", "cu_conc", "temperature_k"),
        tolerance=Tolerance(abs_tol=0.005),
        hints=(
            "Check which concentration you dipped which electrode into.",
            "The Nernst equation uses [Zn2+] over [Cu2+] -- check you have "
            "not written the ratio the other way round.",
            "Your Zn2+ and Cu2+ concentrations look swapped against the "
            "electrodes you described using.",
        ),
    ),
    StepSpec(
        index=1,
        key="delta_g",
        prompt="Calculate Delta-G from your measured Ecell.",
        requires=("ecell",),
        tolerance=Tolerance(rel_tol=0.01),
        hints=(
            "Delta-G uses the number of electrons transferred in this "
            "cell -- check how many that is for Zn/Cu.",
            "Check the sign: this reaction is spontaneous, so Delta-G "
            "should come out negative.",
            "Your value is off by roughly a factor matching F (96500) or "
            "n (2) -- check you have used both constants, not just one.",
        ),
        is_final=True,
    ),
)

register(
    DeterministicPlugin(
        id=EXPERIMENT_ID,
        title="Thermodynamic functions from EMF measurements: Zn-Cu system",
        manual_reference="IACHY102 manual, p.10-15",
        checker=DELTA_G_CHECKER,
        step_specs=STEPS,
        step_checkers={0: ECELL_CHECKER},
    )
)
