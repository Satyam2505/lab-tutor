<!--
tier: C (curated adjacent — NOT the IACHY102 manual)
experiments: exp07
topic: general computational-chemistry troubleshooting (not manual-specific)
-->

# General ORCA / computational chemistry troubleshooting

This describes common, generic reasons a computational chemistry job
fails or looks wrong, independent of any specific manual or exercise. It
is not a substitute for the exact steps or expected output your manual
describes — if this note and the manual ever seem to disagree about what
a specific step should look like, the manual is the authority. Follow it,
and treat this only as background for understanding *why* an error
happens.

## The job did not converge

"Convergence" means the optimisation or the self-consistent-field (SCF)
calculation kept refining its answer until the change between steps fell
below a small threshold. Common generic reasons it does not:

- **A poor starting geometry.** If atoms are placed unreasonably close
  together or the initial structure is far from any real molecular
  shape, the optimiser can struggle to find a sensible minimum.
- **An inappropriate method/basis-set combination** for the system —
  some combinations are simply not well suited to some molecules or
  states.
- **A genuinely flat or complicated potential energy surface**, where
  many geometries have very similar energy and the optimiser oscillates
  between them instead of settling.
- **Too tight a convergence threshold** relative to the precision the
  chosen method/basis set can actually achieve.

## The output file looks empty or incomplete

This usually means the job did not finish — check for an explicit
"normal termination" or completion message near the end of the file
(the exact wording depends on the version and program) rather than
assuming a long file means success. A job that stopped partway through
because it ran out of allotted time, memory, or disk space will often
leave a truncated output with no such message.

## The energy is a large positive number, or "nan"/"inf" appears

This generally indicates the calculation diverged rather than converging
to a physically meaningful answer — often traceable to an unreasonable
starting geometry, a charge or multiplicity specified inconsistently
with the actual molecule, or a numerical instability in a particular
method for that system.

## Two calculations you expected to be comparable give very different
absolute energies

Absolute total energies from quantum chemistry calculations are usually
only meaningful in comparison to another calculation done with the exact
same method, basis set, and (for optimisations) similar convergence
settings. Comparing energies computed with different settings is
comparing two different approximations, not two states of the same
system, and differences produced this way are not chemically meaningful.

## General checklist before concluding something is broken

1. Confirm the input file actually specifies the molecule, method,
   and basis set you intended — a typo in a keyword is far more common
   than a program bug.
2. Confirm the job actually ran to completion rather than being
   interrupted.
3. Re-read the specific output section the exercise asks you to report
   from, rather than skimming the whole file — the number you need is
   often in a clearly labelled block near the end.
4. If none of the above resolves it, this is exactly the kind of
   question worth asking a demonstrator with the actual output file in
   hand, since a specific error message usually narrows the cause
   immediately in a way generic advice cannot.
