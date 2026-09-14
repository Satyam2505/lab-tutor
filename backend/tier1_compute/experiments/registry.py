"""Experiment plugin registry.

A plugin is a *thin config object*: it names the experiment, wires one of
the four shared checker types with the manual's formula and tolerance,
and lists the ordered Socratic steps. It contains no bespoke math.

Three plugin kinds exist:

``DeterministicPlugin``
    The normal case. Tier 1 recomputes and compares; no LLM involved.

``QualitativeOrderingPlugin``
    Experiments 7 and 8 only. These verify a *computational-method
    choice* (ORCA/orbital work), not a measured value, so there is no
    expected-vs-measured check to make. See the module docstring of
    ``exp07_*`` for why this is contained to exactly two experiments.

``PendingManualPlugin``
    A slot whose formulas have not yet been transcribed from the
    IACHY102 manual. It raises on use rather than guessing. This is the
    state every numeric experiment ships in until the manual PDF is
    committed -- see README "Known limitations".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.tier1_compute.shared.base import Checker
from backend.tier1_compute.shared.types import Outcome, StepSpec, Tier1Result


class ManualNotTranscribedError(RuntimeError):
    """Raised when an experiment is used before its manual data exists.

    Deliberately loud. A silent default here would mean shipping invented
    chemistry to students, which is worse than an outage.
    """


class UnknownExperimentError(KeyError):
    pass


@dataclass(frozen=True)
class ExperimentPlugin:
    """Base plugin metadata."""

    id: str
    title: str
    #: Where in the manual the formulas/tolerances come from. Filled in
    #: during transcription so a reviewer can check the numbers.
    manual_reference: str = ""

    @property
    def kind(self) -> str:
        return "base"

    @property
    def is_ready(self) -> bool:
        """False if this experiment cannot be used for real traffic yet."""
        return False

    def steps(self) -> tuple[StepSpec, ...]:
        return ()

    def check(self, inputs: dict[str, Any], reported: float | None) -> Tier1Result:
        raise NotImplementedError

    def check_step(
        self, step_index: int, inputs: dict[str, Any], submitted: float | None
    ) -> Tier1Result:
        raise NotImplementedError

    def compute_expected(self, inputs: dict[str, Any]) -> float:
        """The experiment's value from the student's own data, with no verdict.

        Separate from `check` because the reveal path wants the number
        itself: `check` needs something to compare against and reports
        INVALID without one, which is right for a submission and wrong for
        a reveal.
        """
        raise NotImplementedError


@dataclass(frozen=True)
class DeterministicPlugin(ExperimentPlugin):
    """Wires a shared checker type plus the ordered Socratic steps."""

    checker: Checker | None = None
    step_specs: tuple[StepSpec, ...] = ()
    #: Per-step checkers, keyed by step index. A step with no checker is
    #: procedural (an observation the student confirms) rather than numeric.
    step_checkers: dict[int, Checker] = field(default_factory=dict)

    @property
    def kind(self) -> str:
        return "deterministic"

    @property
    def is_ready(self) -> bool:
        return self.checker is not None

    def steps(self) -> tuple[StepSpec, ...]:
        return self.step_specs

    def check(self, inputs: dict[str, Any], reported: float | None) -> Tier1Result:
        if self.checker is None:
            raise ManualNotTranscribedError(
                f"{self.id}: no checker configured. Transcribe the formula and "
                "tolerance from the IACHY102 manual before enabling this experiment."
            )
        return self.checker.check(inputs, reported)

    def compute_expected(self, inputs: dict[str, Any]) -> float:
        if self.checker is None:
            raise ManualNotTranscribedError(
                f"{self.id}: no checker configured, so no value can be computed."
            )
        return float(self.checker.compute_expected(inputs))

    def check_step(
        self, step_index: int, inputs: dict[str, Any], submitted: float | None
    ) -> Tier1Result:
        """Verify ONE step against the student's own prior data.

        Never compares against the experiment's final answer -- that
        value is not computed on this path at all.
        """
        checker = self.step_checkers.get(step_index)
        if checker is None:
            raise ManualNotTranscribedError(
                f"{self.id}: step {step_index} has no checker configured."
            )
        return checker.check(inputs, submitted)


@dataclass(frozen=True)
class QualitativeOrderingPlugin(ExperimentPlugin):
    """Experiments 7 and 8: relative-ordering checks, not measurements.

    The student reports computed energies for conformers. There is no
    manual formula to recompute, so Tier 1 cannot produce a
    measured-vs-expected verdict. What *can* be checked deterministically
    is the ordering the chemistry requires (e.g. staggered below
    eclipsed). Ordering that is contradicted outright is a determinate
    finding; anything ambiguous is escalated rather than asserted.

    An LLM may be consulted to phrase and sanity-read the student's
    method narrative, but its output is marked low-confidence and biased
    toward escalation -- see `backend/rag/qualitative.py`. This is the
    only place in the system where a model contributes to a judgment
    rather than only phrasing one, and it is confined to these two
    experiments.
    """

    #: (lower_label, higher_label) pairs: the first must come out lower
    #: in energy than the second.
    orderings: tuple[tuple[str, str], ...] = ()
    step_specs: tuple[StepSpec, ...] = ()

    @property
    def kind(self) -> str:
        return "qualitative_ordering"

    @property
    def is_ready(self) -> bool:
        return bool(self.orderings)

    def steps(self) -> tuple[StepSpec, ...]:
        return self.step_specs

    def check(self, inputs: dict[str, Any], reported: float | None) -> Tier1Result:
        """Deterministic part: do the reported energies obey the ordering?

        Returns NOT_APPLICABLE (-> Tier 3) whenever the answer is not
        clear-cut, including when a needed value is missing. Escalating is
        always preferred over asserting here.
        """
        if not self.orderings:
            raise ManualNotTranscribedError(
                f"{self.id}: no orderings configured. Transcribe the expected "
                "conformer comparisons from the manual before enabling."
            )

        energies = inputs.get("energies")
        if not isinstance(energies, dict) or not energies:
            return Tier1Result(
                outcome=Outcome.NOT_APPLICABLE,
                detail={
                    "reason": "no_energies_reported",
                    "confidence": "low",
                    "experiment_kind": self.kind,
                },
            )

        violations: list[dict[str, Any]] = []
        checked = 0
        for lower, higher in self.orderings:
            if lower not in energies or higher not in energies:
                continue
            try:
                lo = float(energies[lower])
                hi = float(energies[higher])
            except (TypeError, ValueError):
                continue
            checked += 1
            if lo >= hi:
                violations.append(
                    {"expected_lower": lower, "expected_higher": higher,
                     "reported_lower": lo, "reported_higher": hi}
                )

        if checked == 0:
            return Tier1Result(
                outcome=Outcome.NOT_APPLICABLE,
                detail={
                    "reason": "no_comparable_pairs_reported",
                    "confidence": "low",
                    "experiment_kind": self.kind,
                },
            )

        if violations:
            from backend.tier1_compute.shared.types import SignatureHit

            return Tier1Result(
                outcome=Outcome.FAIL_WITH_SIGNATURE,
                signature=SignatureHit(
                    code="conformer_ordering_violated",
                    detail=(
                        "The reported energies place a conformer that should be "
                        "the more stable one higher in energy, which points at "
                        "the geometries being swapped or the calculation not "
                        "having converged."
                    ),
                    evidence={"violations": violations},
                ),
                detail={
                    "pairs_checked": checked,
                    "confidence": "low",
                    "experiment_kind": self.kind,
                },
            )

        # Ordering holds. That is necessary but not sufficient -- method
        # choice still needs a human eye, so this is not reported as a pass.
        return Tier1Result(
            outcome=Outcome.NOT_APPLICABLE,
            detail={
                "reason": "ordering_consistent_method_unverified",
                "pairs_checked": checked,
                "confidence": "low",
                "experiment_kind": self.kind,
            },
        )

    def check_step(
        self, step_index: int, inputs: dict[str, Any], submitted: float | None
    ) -> Tier1Result:
        return Tier1Result(
            outcome=Outcome.NOT_APPLICABLE,
            detail={"reason": "qualitative_experiment_has_no_numeric_steps"},
        )


@dataclass(frozen=True)
class PendingManualPlugin(ExperimentPlugin):
    """A registered experiment whose manual data has not been transcribed."""

    reason: str = "IACHY102 manual not present in the repository"

    @property
    def kind(self) -> str:
        return "pending_manual"

    @property
    def is_ready(self) -> bool:
        return False

    def check(self, inputs: dict[str, Any], reported: float | None) -> Tier1Result:
        raise ManualNotTranscribedError(f"{self.id} ({self.title}): {self.reason}")

    def check_step(
        self, step_index: int, inputs: dict[str, Any], submitted: float | None
    ) -> Tier1Result:
        raise ManualNotTranscribedError(f"{self.id} ({self.title}): {self.reason}")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, ExperimentPlugin] = {}


def register(plugin: ExperimentPlugin) -> ExperimentPlugin:
    if plugin.id in _REGISTRY:
        raise ValueError(f"Duplicate experiment id: {plugin.id}")
    _REGISTRY[plugin.id] = plugin
    return plugin


def get_plugin(experiment_id: str) -> ExperimentPlugin:
    try:
        return _REGISTRY[experiment_id]
    except KeyError as exc:
        raise UnknownExperimentError(
            f"No plugin registered for experiment '{experiment_id}'"
        ) from exc


def all_plugins() -> list[ExperimentPlugin]:
    return [_REGISTRY[k] for k in sorted(_REGISTRY)]


def ready_plugins() -> list[ExperimentPlugin]:
    return [p for p in all_plugins() if p.is_ready]


def reset_registry_for_tests() -> None:
    _REGISTRY.clear()
