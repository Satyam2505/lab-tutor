<!--
tier: C (curated adjacent — NOT the IACHY102 manual)
experiments: exp08
topic: general conformational analysis background (torsional strain, steric effects)
-->

# Conformational analysis: background for ethane and cyclohexane

General organic chemistry background on why conformers differ in
energy. Not the manual's procedure — treat this as the "why", with the
manual as the authority on the "what to do and report".

## Conformers, in general

Conformers are different three-dimensional arrangements of the same
molecule that interconvert by rotation around single bonds, without
breaking any bonds. Because the underlying connectivity is identical,
conformers are not different compounds — they are different snapshots of
one molecule's accessible shapes, each with its own potential energy.

## Ethane: staggered vs. eclipsed

Looking down the C–C bond of ethane (a Newman projection), the
**staggered** conformation has the hydrogens on the front carbon
positioned exactly between the hydrogens on the back carbon (60° apart),
while the **eclipsed** conformation has them lined up directly behind
each other (0° apart).

The staggered conformer is lower in energy. The accepted explanation
combines two effects:

- **Steric strain**: eclipsed hydrogens are closer to each other,
  increasing repulsion between their electron clouds.
- **Torsional strain (hyperconjugation)**: in the staggered form, a
  filled C–H bonding orbital on one carbon can donate a small amount of
  electron density into an empty, antibonding C–H orbital on the other
  carbon, a stabilising interaction that is geometrically disfavoured in
  the eclipsed form. Modern treatments generally consider this
  hyperconjugative effect, not steric bulk alone, as the larger
  contributor to ethane's rotational barrier, though both matter.

The energy difference between the two (the rotational barrier) is small
enough that ethane rotates freely at room temperature — the two forms
are not isolable species, only more- and less-populated points along a
continuous rotation.

## Cyclohexane: chair vs. boat (and twist-boat)

Cyclohexane's ring can pucker into several distinct shapes:

- **Chair**: every ring carbon is staggered relative to its neighbours,
  and all bond angles are close to the ideal tetrahedral angle. This is
  the lowest-energy, dominant conformation at room temperature — the
  large majority of cyclohexane molecules are in a chair form at any
  given moment.
- **Boat**: two carbons pucker up out of the ring plane on the same
  side. The boat conformation has both eclipsing interactions along its
  "sides" and a steric clash between the two flagpole hydrogens that
  point toward each other at the raised carbons, making it substantially
  higher in energy than the chair.
- **Twist-boat**: a distortion of the boat that relieves some of the
  eclipsing and flagpole strain by twisting the ring slightly. It sits
  between the chair and boat in energy — more stable than the boat, but
  still well above the chair.

The two chair forms of cyclohexane interconvert by a "ring flip", which
passes through higher-energy twist-boat and boat-like geometries along
the way; this is why a computational study of these conformers reports
several energies rather than just one.

## Reading a relative-stability comparison

When a set of computed conformer energies is compared, only the
*relative* ordering (which is lower than which) and the *relative*
magnitude (how much lower) are usually chemically meaningful — the
absolute total energy of any one geometry, on its own, is not
interpretable without such a comparison. This is a general property of
how these calculations are read, independent of which software produced
the numbers.
