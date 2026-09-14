<!--
tier: C (curated adjacent — NOT the IACHY102 manual)
experiments: exp07
topic: general molecular orbital theory background
-->

# Molecular orbital theory: background for the HOMO/LUMO exercise

This is general quantum-chemistry background, not the manual's
procedure. It exists to answer "why" questions the manual itself does
not have to — a student is not assessed on this text, and no formula or
step here should be quoted as if the manual said it.

## What a molecular orbital is

A molecular orbital (MO) is a wavefunction describing where an electron
is likely to be found across an entire molecule, formed by mathematically
combining the atomic orbitals of the atoms that make up the molecule
(the linear combination of atomic orbitals, or LCAO, approach). Each MO
has an associated energy. Filling the lowest-energy MOs first with the
molecule's electrons (two per orbital, opposite spin) gives the ground
state.

## HOMO and LUMO

- **HOMO** (Highest Occupied Molecular Orbital): the filled orbital with
  the highest energy. Loosely, this is where the molecule's most
  "available" electrons sit.
- **LUMO** (Lowest Unoccupied Molecular Orbital): the empty orbital with
  the lowest energy — the first place an added electron would go, or the
  orbital most likely to accept electron density in a reaction.
- The HOMO-LUMO energy gap is a rough proxy for a molecule's kinetic and
  optical stability: a large gap generally means the molecule is less
  reactive and absorbs higher-energy (shorter-wavelength) light than a
  molecule with a small gap.

For a small, symmetric molecule like methane, several MOs can be close
in energy or degenerate (identical energy) by symmetry — this is normal
and is a property of the molecule's point group, not a sign of a failed
calculation.

## Why basis sets and functionals matter

A quantum chemistry program cannot represent an orbital exactly; it
approximates it as a combination of simpler mathematical functions
(basis functions). A **basis set** is the specific collection of those
functions used for each atom:

- Larger basis sets (more functions per atom) generally give more
  accurate energies and geometries, at greater computational cost.
- Different basis sets can give noticeably different absolute energies
  for the same molecule — this is expected and is why a comparison
  between two calculations is only meaningful when both used the *same*
  basis set and method.

A **functional** (in density functional theory, DFT) is the mathematical
recipe used to approximate the exchange-correlation energy — the part of
the true electronic energy that DFT cannot compute exactly. Different
functionals (B3LYP, PBE0, and many others) trade off accuracy for
different properties (energies, geometries, orbital energies) against
computational cost. There is no single "best" functional for every
purpose; a functional and basis set are usually chosen together as a
combination that has been validated for the property being studied.

## Reading orbital contributions

An "orbital contribution" is typically the percentage weight that a
particular atom's or fragment's atomic orbitals contribute to a given
molecular orbital. A HOMO that is heavily weighted on one atom, for
instance, suggests that atom's local electron density dominates the
molecule's highest-energy filled state. This is background for
interpreting an orbital analysis output in general; the specific table
or output format you are asked to fill in comes from the manual and
software you are actually using, not from this note.
