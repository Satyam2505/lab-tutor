<!--
tier: C (curated adjacent — NOT the IACHY102 manual)
experiments: exp02
topic: general reaction kinetics background (integrated rate laws, pseudo-order, Arrhenius, catalysis)
-->

# Reaction kinetics background: acid-catalysed ester hydrolysis

General kinetics theory. The manual's own stated formulas, tolerances
and titration procedure for this experiment are the authority for what
to actually calculate and report — use this only for the underlying
"why".

## Order and molecularity

**Molecularity** is a mechanistic concept: the number of molecules that
come together in a single elementary reaction step (unimolecular,
bimolecular, and so on). **Order** is an experimentally observed
quantity: the power to which a species' concentration is raised in the
empirical rate law. For a reaction with a single elementary step, order
and molecularity coincide; for a multi-step mechanism they generally do
not, and order must be determined from data rather than assumed from the
overall stoichiometric equation.

## Integrated rate laws

A rate law expressed as a differential equation (rate as a function of
concentration) can be integrated with respect to time to give
concentration as an explicit function of time — the form actually used
to analyse experimental data:

- **Zero order**: [A] decreases linearly with time.
- **First order**: ln[A] decreases linearly with time; the rate constant
  is the (negative) slope of that line, and the half-life is
  concentration-independent (a constant for a given rate constant).
- **Second order**: 1/[A] increases linearly with time.

Plotting data in the form appropriate to a candidate order (and checking
which plot is actually linear) is a standard way to determine order
experimentally, independent of the specific reaction.

## Pseudo-order kinetics

When a reaction technically depends on more than one species'
concentration, but one of them is present in such large excess that its
concentration barely changes over the course of the reaction (e.g. water
in an aqueous hydrolysis, or a large excess of one reactant), the
reaction behaves *as if* it depended only on the other species. This is
called a pseudo-order reaction: a bimolecular reaction can behave as
pseudo-first-order if only one reactant's concentration is actually
changing enough to matter kinetically. The *true* rate constant (with
respect to both species) can be recovered from the pseudo-rate constant
by dividing out the (approximately constant) concentration of the
species in excess, when that value is known.

## Acid catalysis, generally

An acid catalyst provides an alternative reaction pathway with a lower
activation energy — commonly by protonating a reactive site on the
substrate, making it more susceptible to attack — without itself being
consumed by the overall reaction. Because the catalyst's concentration
does not change, its effect shows up as a constant multiplicative factor
in the observed rate rather than as a changing concentration term in the
rate law, which is part of why acid-catalysed hydrolyses are often
studied under pseudo-order conditions.

## The Arrhenius equation

The Arrhenius equation, k = A·exp(−Ea/RT), relates a reaction's rate
constant k to temperature T, describing how reaction rate typically
increases with temperature: A is the pre-exponential (frequency) factor,
Ea is the activation energy, and R is the gas constant. Plotting ln(k)
against 1/T for measurements taken at several temperatures gives a
straight line whose slope is −Ea/R — a standard way activation energy is
determined experimentally, though it requires rate constants measured at
more than one temperature and is not part of every kinetics experiment.

## Reading a titration-based kinetics experiment, generally

In a reaction followed by withdrawing samples and titrating them,
subsequent stages of the reaction are usually effectively stopped in the
withdrawn sample (commonly by rapid cooling, dilution, or a change in
another condition) so that the titration reflects the composition at the
moment of withdrawal rather than continuing to react on the bench. An
"infinity" reading — the titration value once the reaction has gone to
completion — is a common reference point subtracted from earlier
readings for exactly the reagents your specific procedure follows; the
manual's own procedure and formula are what determine the precise
combination to use here.
