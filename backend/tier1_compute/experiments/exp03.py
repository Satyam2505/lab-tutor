"""Experiment 03 -- Colorimetric estimation of Ni2+ (conventional method
only; the smartphone/RGB variant is a separate, unimplemented data shape
-- see the note at the bottom) (IACHY102 manual, p.20-23).

STATUS: implemented (conventional colorimetry only), with tolerance/fit-
quality DEFAULTS the manual does not state (see below). Unblocks
Socratic session-start for this experiment.

The manual's procedure (p.22): standards at 2, 4, 6, 8 ppm Ni2+, plus one
unknown, absorbance read at 440 nm against a Ni(dmg)2/K3[Fe(CN)6] blank.
Beer's law: A = epsilon*c*l, i.e. a straight-line calibration through
(approximately) the origin -- exactly `CalibrationCurveChecker`'s shape,
solving for concentration (`solve_for="x"`) from the unknown's measured
absorbance.

The manual gives no experiment-specific numeric tolerance or fit-quality
floor and no worked numeric example (Table 1, p.23, is printed blank for
the student's own run -- see manual/IACHY102_manual.md's summary table).
`tolerance` and `min_r_squared` below are deliberate engineering defaults
for a self-consistency check, not manual-derived values.

NOT implemented here: the smartphone/RGB-ratio variant the same manual
section describes (p.22-23), which calibrates against an R/G, G/B or R/B
ratio rather than an absorbance -- a different, still-not-yet-decided
input shape (which ratio is "the" calibration axis is chosen per-run,
not fixed), and a separate judgment call from the conventional method
implemented here.
"""

from __future__ import annotations

from backend.tier1_compute.experiments.registry import DeterministicPlugin, register
from backend.tier1_compute.shared import CalibrationCurveChecker, StepSpec, Tolerance

EXPERIMENT_ID = "exp03"

FINAL_CHECKER = CalibrationCurveChecker(
    standards_x_key="standard_conc_ppm",
    standards_y_key="standard_absorbance",
    unknown_y_key="unknown_absorbance",
    tolerance=Tolerance(rel_tol=0.05),  # DEFAULT -- see module docstring
    min_r_squared=0.98,  # DEFAULT -- see module docstring
    min_standards=4,  # manual's own procedure: 2/4/6/8 ppm, p.22
    solve_for="x",
    label="Ni2+ concentration (conventional colorimetry, 440 nm)",
)

STEPS: tuple[StepSpec, ...] = (
    StepSpec(
        index=0,
        key="standards_and_unknown",
        prompt=(
            "Record the concentration and absorbance of each standard "
            "(2/4/6/8 ppm) and the absorbance of the unknown, all at "
            "440 nm against the NaOH blank."
        ),
        requires=("standard_conc_ppm", "standard_absorbance", "unknown_absorbance"),
        hints=(
            "Check you measured every standard against the same blank.",
            "Check your absorbance readings actually increase with "
            "concentration in the order 2, 4, 6, 8 ppm.",
            "One of your standard absorbances is out of order relative to "
            "its concentration -- check for a transcription or dilution "
            "mistake on that flask.",
        ),
    ),
    StepSpec(
        index=1,
        key="unknown_concentration",
        prompt="Plot the calibration curve and read off the unknown's concentration.",
        requires=("standard_conc_ppm", "standard_absorbance", "unknown_absorbance"),
        tolerance=Tolerance(rel_tol=0.05),
        hints=(
            "Check your calibration line actually passes close to the origin.",
            "Your standards do not sit close to a straight line -- check "
            "for one outlier flask before reading off the unknown.",
            "The unknown's absorbance falls outside the range your "
            "standards cover, so reading it off this line is an "
            "extrapolation, not a calibrated measurement.",
        ),
        is_final=True,
    ),
)

register(
    DeterministicPlugin(
        id=EXPERIMENT_ID,
        title="Colorimetric estimation of Ni2+ (conventional method)",
        manual_reference="IACHY102 manual, p.20-23",
        checker=FINAL_CHECKER,
        step_specs=STEPS,
        step_checkers={1: FINAL_CHECKER},
    )
)
