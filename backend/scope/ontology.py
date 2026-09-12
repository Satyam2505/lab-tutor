"""What each experiment is *about*, for routing purposes only.

## Read this before adding anything to this file

The vocabulary below is **routing vocabulary, not manual content.** Its
only job is to decide *which experiment a question belongs to* so that a
question about ORCA does not retrieve colorimetry chunks. It is never a
source of answers, it is never cited, and nothing here may be used to
tell a student what a procedure is.

The distinction matters because the two things have different evidence
requirements. Knowing that "HOMO" belongs to experiment 7 is a routing
fact, and getting it wrong costs a bad retrieval. Knowing *what the
manual instructs you to do with the HOMO* is manual content, and getting
it wrong means inventing chemistry for a student being assessed on it.

## Provenance of what is here

Experiments 2, 3, 7 and 8 are populated from the topic lists supplied in
the Phase 1 brief, which enumerated their subject matter directly
(Gabedit/ORCA/Avogadro and HOMO/LUMO for 7; ethane and cyclohexane
conformers for 8; ethyl acetate hydrolysis for 2; Ni(II) colorimetry and
the smartphone RGB method for 3). That is `SourceTier.OFFICIAL_SUPPLEMENTARY`
in spirit: enough to route on, not enough to answer from.

Experiments 1, 4, 5, 6, 9 and 10 are **unpopulated**, because nothing in
this repository or in the brief establishes what they are. The IACHY102
manual is not present (see `docs/current_state_audit.md` §0), and
inventing plausible first-year chemistry titles for them would produce a
router that confidently misroutes real student questions.

They are therefore declared with `status=UNKNOWN_PENDING_MANUAL`, and
`route()` returns `None` for them rather than guessing. A question that
cannot be routed is still recognised as in-domain and handled — it
becomes `IN_SCOPE_RETRIEVAL_INSUFFICIENT`, not `OUT_OF_SCOPE`. That is
the correct behaviour for "I know this is chemistry, I cannot tell you
which experiment", and it degrades honestly instead of silently.

**Populating the remaining six is the first task in Phase 2** and takes
about an hour once the PDF exists. See `docs/handoff_phase2.md`.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

ALL_EXPERIMENT_IDS: tuple[str, ...] = tuple(f"exp{n:02d}" for n in range(1, 11))

#: Testing/validation priority from the brief. Product coverage is all
#: ten; this orders only where evaluation effort goes.
PRIORITY: dict[str, str] = {
    "exp07": "P0+",
    "exp02": "P0",
    "exp03": "P0",
    "exp08": "P0",
    "exp01": "P1",
    "exp04": "P1",
    "exp05": "P1",
    "exp06": "P1",
    "exp09": "P1",
    "exp10": "P1",
}


class TopicStatus(str, enum.Enum):
    #: Subject matter established by the Phase 1 brief. Routable.
    KNOWN_FROM_BRIEF = "known_from_brief"
    #: Subject matter not established by any source available here.
    UNKNOWN_PENDING_MANUAL = "unknown_pending_manual"


@dataclass(frozen=True)
class ExperimentTopic:
    """Routing vocabulary for one experiment. Not an answer source."""

    id: str
    #: Working title. Under `UNKNOWN_PENDING_MANUAL` this is a
    #: placeholder and must not be shown to a student as the manual's
    #: title for the experiment.
    title: str
    status: TopicStatus
    #: Terms that are strongly discriminative: seeing one is close to
    #: decisive for this experiment.
    strong_terms: frozenset[str] = field(default_factory=frozenset)
    #: Terms that are suggestive but shared with other experiments.
    weak_terms: frozenset[str] = field(default_factory=frozenset)
    #: Software the experiment uses. Strong signal, but shared between
    #: the two computational experiments, so weighted between the two.
    software: frozenset[str] = field(default_factory=frozenset)
    provenance: str = ""

    @property
    def routable(self) -> bool:
        return self.status is TopicStatus.KNOWN_FROM_BRIEF and bool(
            self.strong_terms or self.weak_terms or self.software
        )

    @property
    def priority(self) -> str:
        return PRIORITY[self.id]


def _t(*words: str) -> frozenset[str]:
    return frozenset(words)


_BRIEF = "Phase 1 brief topic list; routing only, pending IACHY102 confirmation"

_TOPICS: dict[str, ExperimentTopic] = {}


def _add(topic: ExperimentTopic) -> None:
    _TOPICS[topic.id] = topic


# --- P0+: experiment 7 ------------------------------------------------------

_add(
    ExperimentTopic(
        id="exp07",
        title="Molecular orbitals of methane and oxygen (computational)",
        status=TopicStatus.KNOWN_FROM_BRIEF,
        strong_terms=_t(
            "homo", "lumo", "orbital", "orbitals", "orbital contribution",
            "orbital contributions", "orbital energy", "molecular orbital",
            "isosurface", "methane", "ch4", "o2", "dioxygen",
            "orbital coefficient", "mo diagram",
        ),
        weak_terms=_t(
            "basis", "basis set", "functional", "method", "optimisation",
            "optimise", "geometry", "structure", "input", "output",
            "final energy", "single point", "converged", "convergence",
            "job", "calculation", "visualise", "visualisation",
            "molecule", "oxygen", "contribution", "table",
        ),
        software=_t("gabedit", "orca", "avogadro"),
        provenance=_BRIEF,
    )
)

# --- P0: experiment 8 -------------------------------------------------------

_add(
    ExperimentTopic(
        id="exp08",
        title="Conformational analysis of ethane and cyclohexane (computational)",
        status=TopicStatus.KNOWN_FROM_BRIEF,
        strong_terms=_t(
            "staggered", "eclipsed", "chair", "boat", "conformer",
            "conformers", "conformation", "conformations", "conformational",
            "cyclohexane", "ethane", "dihedral", "torsional", "torsion",
            "newman", "anti", "gauche", "ring flip",
            "potential energy profile", "energy profile",
        ),
        weak_terms=_t(
            "stability", "stable", "energy", "energies", "barrier",
            "optimisation", "optimise", "geometry", "structure",
            "relative energy", "strain", "steric", "rotation",
        ),
        software=_t("avogadro", "orca", "gabedit"),
        provenance=_BRIEF,
    )
)

# --- P0: experiment 2 -------------------------------------------------------

_add(
    ExperimentTopic(
        id="exp02",
        title="Acid-catalysed hydrolysis of ethyl acetate (kinetics)",
        status=TopicStatus.KNOWN_FROM_BRIEF,
        strong_terms=_t(
            "ethyl acetate", "hydrolysis", "pseudo", "pseudo first order",
            "pseudo-first-order", "rate constant", "molecularity",
            "ester", "acid catalysed", "acid-catalysed", "acid catalyzed",
            "kinetics", "order of reaction", "half life",
        ),
        weak_terms=_t(
            "rate", "order", "time", "titration", "titre", "aliquot",
            "alkali", "sodium hydroxide", "naoh", "hcl", "slope",
            "log", "concentration", "reaction", "catalyst", "withdraw",
            "quench", "infinity reading", "burette",
        ),
        software=frozenset(),
        provenance=_BRIEF,
    )
)

# --- P0: experiment 3 -------------------------------------------------------

_add(
    ExperimentTopic(
        id="exp03",
        title="Colorimetric and smartphone determination of Ni(II)",
        status=TopicStatus.KNOWN_FROM_BRIEF,
        strong_terms=_t(
            "colorimetry", "colorimeter", "calibration curve", "beer",
            "beer lambert", "beer-lambert", "absorbance", "nickel",
            "ni2", "ni2+", "ni(ii)", "rgb", "smartphone", "camera",
            "image", "photo", "r/g", "r/b", "g/b", "colour intensity",
            "color intensity", "cuvette", "transmittance",
        ),
        weak_terms=_t(
            "standard", "standards", "unknown", "concentration",
            "calibration", "wavelength", "filter", "blank", "dilution",
            "linear", "slope", "intercept", "graph", "plot", "green",
            "intensity", "sample",
        ),
        software=frozenset(),
        provenance=_BRIEF,
    )
)

# --- P1: subject matter not established -------------------------------------
#
# Deliberately empty. See the module docstring: a guessed title here
# becomes a confidently misrouted student question.

for _unknown in ("exp01", "exp04", "exp05", "exp06", "exp09", "exp10"):
    _add(
        ExperimentTopic(
            id=_unknown,
            title=f"Experiment {int(_unknown[3:])} (subject matter pending IACHY102)",
            status=TopicStatus.UNKNOWN_PENDING_MANUAL,
            provenance=(
                "Not established by any source available to this phase. "
                "Populate from the manual before relying on routing."
            ),
        )
    )


# ---------------------------------------------------------------------------
# General domain vocabulary
# ---------------------------------------------------------------------------

#: Vocabulary that marks a question as belonging to this product's world
#: even when it names no experiment. "what is a burette" is in-domain and
#: unroutable, which is a real and common case, not an error.
GENERAL_DOMAIN_TERMS: frozenset[str] = frozenset(
    {
        "experiment", "laboratory", "lab", "practical", "manual",
        "procedure", "observation", "reading", "result", "record",
        "calculation", "formula", "equation", "table", "graph", "plot",
        "chemistry", "chemical", "reagent", "solution", "solutions",
        "titration", "titrate", "burette", "pipette", "flask", "beaker",
        "meniscus", "endpoint", "equivalence", "normality", "molarity",
        "molar", "mole", "moles", "aliquot", "standard", "blank",
        "dilution", "dilute", "concentration", "absorbance", "sample",
        "temperature", "weigh", "weighing", "balance", "apparatus",
        "viva", "record book", "submission", "reading",
        "molecule", "molecular", "atom", "bond", "energy", "electron",
        "structure", "geometry", "optimisation", "calculation",
        "software", "input", "output", "file", "button", "option",
        "screen", "window", "menu", "click", "screenshot", "figure",
        "step", "steps",
    }
)

#: The subset of GENERAL_DOMAIN_TERMS too generic, alone, to overrule
#: positive out-of-domain evidence. "software" and "lab" appear in
#: ordinary off-topic phrases too ("software engineering interview", "lab
#: report" -- the latter already an OFF_SCOPE trigger phrase in
#: `socratic_engine/triage.py`), so a lone hit here must not by itself
#: block a refusal the way a real chemistry term ("burette", "titration",
#: "molecule") should. Found by the golden QA generator's own
#: verification against the live classifier
#: (`golden_dataset/qa/generate_qa.py`) refusing to write two cases whose
#: expected OUT_OF_SCOPE outcome the classifier did not actually produce.
_WEAK_GENERIC_DOMAIN_TERMS: frozenset[str] = frozenset(
    {
        "experiment", "laboratory", "lab", "practical", "manual",
        "procedure", "record", "software", "input", "output", "file",
        "step", "steps", "result", "reading",
    }
)

#: Software names, wherever they appear. Strong in-domain evidence.
SOFTWARE_TERMS: frozenset[str] = frozenset(
    {"gabedit", "orca", "avogadro", "chemcraft", "molden"}
)

#: Vocabulary that marks a question as belonging to a different world.
#: Narrow on purpose: over-matching here refuses a legitimate question,
#: which teaches a student the tool is broken. The scope classifier
#: requires these to appear *without* competing in-domain evidence.
OUT_OF_DOMAIN_TERMS: frozenset[str] = frozenset(
    {
        "gpu", "gaming", "game", "fps", "laptop", "phone deal", "cricket",
        "football", "movie", "netflix", "song", "instagram", "whatsapp",
        "girlfriend", "boyfriend", "placement", "internship", "resume",
        "cv", "salary", "interview", "leetcode", "dsa", "python script",
        "java", "javascript", "html", "css", "react", "compiler",
        "operating system", "dbms", "networks", "calculus", "integration",
        "differentiation", "physics assignment", "history", "geography",
        "economics", "recipe", "weather", "joke", "poem", "essay",
        "biology", "anatomy", "medicine", "stock", "crypto", "bitcoin",
    }
)

#: Markers that a question is asking for background or theory rather than
#: the documented procedure. Pushes toward Level 2 (adjacent).
ADJACENT_MARKERS: frozenset[str] = frozenset(
    {
        "why does", "why do", "physically", "theory", "theoretical",
        "intuition", "intuitively", "derive", "derivation", "proof",
        "prove", "fundamentally", "underlying", "real reason",
        "in general", "generally", "alternative", "instead of",
        "compared to", "comparison", "better than", "difference between",
        "what if i used", "could i use", "other method", "another method",
        "more accurate", "advantage", "disadvantage", "limitation",
        "limitations", "assumption", "assumptions", "background",
        "history", "who discovered", "deeper", "explain the concept",
    }
)

#: Markers that a question is asking for the documented procedure itself.
#: Pushes toward Level 1 (direct).
PROCEDURAL_MARKERS: frozenset[str] = frozenset(
    {
        "how to", "how do", "how can", "where is", "where do", "which",
        "what do i", "what should i", "steps", "step", "procedure",
        "next", "after", "before", "button", "option", "menu", "click",
        "screen", "window", "tab", "fill", "table", "record", "note",
        "formula", "equation", "calculate", "value", "reading",
        "required", "need to", "supposed to", "manual says", "given",
    }
)


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------


def get_topic(experiment_id: str) -> ExperimentTopic:
    try:
        return _TOPICS[experiment_id]
    except KeyError as exc:
        raise KeyError(f"No ontology entry for '{experiment_id}'") from exc


def all_topics() -> list[ExperimentTopic]:
    return [_TOPICS[k] for k in sorted(_TOPICS)]


def routable_topics() -> list[ExperimentTopic]:
    return [t for t in all_topics() if t.routable]


def unroutable_topics() -> list[ExperimentTopic]:
    """Experiments declared but not yet populated. Reported, not hidden."""
    return [t for t in all_topics() if not t.routable]


def coverage_report() -> dict[str, object]:
    """Machine-readable statement of what routing actually covers."""
    routable = routable_topics()
    return {
        "experiments_declared": len(_TOPICS),
        "experiments_routable": len(routable),
        "routable_ids": [t.id for t in routable],
        "pending_manual_ids": [t.id for t in unroutable_topics()],
        "blocked_by": "IACHY102 manual absent; see docs/current_state_audit.md",
    }
