"""Turning what a student actually types into something routable.

Real traffic in a VIT lab does not look like a benchmark. It looks like:

    "exp 7 mein orca input kaha se banau"
    "bhai gabedit me woh option kidhar hai"
    "mera orca run nahi hora"
    "whyy my orbitl contributon not comming"

Normalisation has exactly one job: make the *intent* legible to the
router without changing the *science*. That asymmetry drives every
decision in this module.

Specifically:

* Hinglish and Romanised Hindi function words are mapped to English
  equivalents ("kaha"/"kidhar" -> "where", "kaise" -> "how"). These are
  question words and postpositions; translating them cannot change what
  chemistry is being asked about.

* Domain terms are spell-corrected against a closed vocabulary
  (`DOMAIN_VOCABULARY`) using conservative edit distance. "orbitl" ->
  "orbital" is safe because "orbitl" is not a word.

* **Chemical identifiers are never corrected.** "CH4" stays "CH4".
  "Ni2+" stays "Ni2+". A spell-corrector that helpfully turns "NO2" into
  "NO3", or "chloride" into "chlorate", has changed the question into a
  different question and will be confidently wrong about it. Anything
  matching `_CHEMICAL_RE` is passed through untouched, and
  `test_normalisation.py` asserts this for a list of pairs that differ
  by one character.

* Nothing is deleted that carries meaning. Filler ("bhai", "plz") goes;
  negation ("nahi", "not") is preserved and mapped, because "mera orca
  run nahi hora" and "mera orca run hora" are opposite reports.

No model is called here. Normalisation runs before routing, and routing
must work when inference is unreachable.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Vocabularies
# ---------------------------------------------------------------------------

#: Romanised Hindi / Hinglish function words -> English. Question words,
#: postpositions, auxiliaries and negation only. No content words: this
#: table must not be able to change which substance or which step is
#: being discussed.
HINGLISH_FUNCTION_WORDS: dict[str, str] = {
    # question words
    "kaise": "how", "kese": "how", "kaisay": "how", "kaisi": "how", "kaisa": "how",
    "kaha": "where", "kahan": "where", "kaha'n": "where", "kidhar": "where",
    "kithar": "where", "kahaan": "where",
    "kyu": "why", "kyun": "why", "kyo": "why", "kyun ki": "because",
    "kya": "what", "kyaa": "what", "kaun": "which", "konsa": "which",
    "konsi": "which", "kaunsa": "which", "kaunsi": "which",
    "kab": "when", "kitna": "how much", "kitne": "how many", "kitni": "how much",
    # postpositions / particles
    #
    # Hinglish/English homographs are deliberately absent from this table.
    # "is", "us", "to", "me", "na" and "par" are all ordinary Hindi
    # particles AND ordinary English words, and mapping them would rewrite
    # "tell me what is next" into "tell in what this next". The routing
    # value of a postposition is close to zero, so the safe choice is to
    # leave every ambiguous one alone.
    "ka": "of", "ki": "of", "ke": "of", "mein": "in", "mai": "in",
    "se": "from", "ko": "to", "tak": "until",
    "wala": "one", "wali": "one", "waala": "one",
    # demonstratives
    "woh": "that", "wo": "that", "ye": "this", "yeh": "this",
    "isme": "in this", "usme": "in that",
    # verbs of asking/doing, kept generic
    "banau": "make", "banaye": "make", "banana": "make", "banega": "made",
    "banaun": "make", "banau'n": "make",
    "nikale": "calculate", "nikalna": "calculate", "nikalu": "calculate",
    "nikalein": "calculate", "nikaale": "calculate",
    "dekhu": "see", "dekhe": "see", "dekhna": "see", "dekhen": "see",
    "dekhta": "see", "dikhega": "shown",
    "milega": "found", "milta": "found", "milegi": "found", "mile": "found",
    "karu": "do", "karna": "do", "kare": "do", "karein": "do", "karta": "do",
    "hota": "is", "hai": "is", "hain": "are", "tha": "was",
    "hora": "happening", "horaha": "happening", "raha": "happening",
    "chalega": "work", "chalta": "works", "chal": "run",
    "lagega": "take", "lagta": "seems",
    "samajh": "understand", "samjha": "understood",
    "batao": "tell", "bata": "tell", "bataye": "tell",
    "chahiye": "need", "chaiye": "need",
    # negation -- preserved deliberately, never dropped. "mera orca run
    # nahi hora" and "mera orca run hora" are opposite reports.
    "nahi": "not", "nahin": "not", "nai": "not",
    "bina": "without", "koi": "any",
    # conjunctions
    "aur": "and", "ya": "or", "lekin": "but", "phir": "then", "fir": "then",
    "agar": "if", "toh": "then", "jab": "when", "bhi": "also",
    "abhi": "now", "baad": "after", "pehle": "before", "sath": "with",
    "mera": "my", "meri": "my", "apna": "my",
}

#: Pure filler. Carries no propositional content, so dropping it is safe.
FILLER_WORDS: frozenset[str] = frozenset(
    {
        "bhai", "bhaiya", "yaar", "yar", "bro", "sir", "maam", "madam",
        "plz", "pls", "please", "kindly", "thanks", "thanku", "ty",
        "actually", "basically", "literally", "just", "like", "um", "uh",
        "hello", "hi", "hey", "namaste", "guys",
    }
)

#: Shorthand that expands to something the router looks for.
SHORTHAND: dict[str, str] = {
    "exp": "experiment", "expt": "experiment", "ex": "experiment",
    "lab": "laboratory",
    "calc": "calculation", "calcs": "calculations",
    "opt": "optimisation", "optimization": "optimisation",
    "optimize": "optimise", "optimized": "optimised",
    "geom": "geometry",
    "struct": "structure",
    "conc": "concentration", "concn": "concentration",
    "abs": "absorbance",
    "temp": "temperature",
    "soln": "solution", "sol": "solution",
    "rxn": "reaction",
    "eqn": "equation", "eq": "equation",
    "govt": "government",
    "info": "information",
    "pic": "screenshot", "pics": "screenshots", "img": "image",
    "ss": "screenshot",
    "ur": "your",
    "cant": "cannot", "dont": "do not", "doesnt": "does not",
    "isnt": "is not", "wont": "will not", "im": "i am", "ive": "i have",
    "whats": "what is", "hows": "how is", "wheres": "where is",
    # No single-letter entries, ever. In this domain a lone letter is far
    # more likely to be a scientific symbol than chat shorthand: "k" is
    # the rate constant in experiment 2, "N" is normality, "n" is reaction
    # order, "V" is volume, "R" is the gas constant. An earlier revision
    # mapped "k" -> "ok" and turned "ethyl acetate ka k kaise nikale" into
    # a question about nothing. See `_is_symbol`.
}

#: Lone letters that are scientific symbols here. Protected from every
#: rewrite, including case folding into a shorthand lookup.
SCIENTIFIC_SYMBOLS: frozenset[str] = frozenset(
    "knvrtampxyzc"
)

#: The closed vocabulary spell-correction is allowed to snap to. Terms
#: only -- adding a word here means "a student misspelling this should be
#: corrected", so it must be a term whose neighbours in edit-distance
#: space are not *other* meaningful terms.
DOMAIN_VOCABULARY: frozenset[str] = frozenset(
    {
        # software
        "gabedit", "orca", "avogadro", "chemcraft", "molden", "notepad",
        # computational chemistry
        "optimisation", "optimise", "geometry", "structure", "molecule",
        "molecular", "orbital", "orbitals", "energy", "energies",
        "basis", "functional", "method", "calculation", "convergence",
        "converged", "input", "output", "keyword", "coordinates",
        "homo", "lumo", "contribution", "contributions", "visualise",
        "visualisation", "isosurface", "conformer", "conformation",
        "conformational", "dihedral", "torsional", "staggered", "eclipsed",
        "cyclohexane", "chair", "boat", "ethane", "methane", "oxygen",
        "stability", "stable", "singlepoint",
        # wet lab
        "titration", "titrate", "burette", "pipette", "flask", "beaker",
        "meniscus", "endpoint", "equivalence", "normality", "molarity",
        "aliquot", "standard", "standardisation", "blank", "reagent",
        "absorbance", "colorimetry", "colorimeter", "calibration",
        "concentration", "wavelength", "transmittance", "cuvette",
        "spectrophotometer", "hydrolysis", "kinetics", "catalysed",
        "catalyst", "pseudo", "rate", "constant", "order", "molecularity",
        "conductance", "conductivity", "electrode", "potential",
        "viscosity", "solution", "dilution", "temperature",
        # experiment-specific nouns
        "ester", "acetate", "acid", "alkali", "sodium", "hydroxide",
        "nickel", "complex", "smartphone", "calibrate", "unknown",
        # generic question vocabulary that students misspell
        "procedure", "observation", "table", "graph", "plot", "screenshot",
        "button", "option", "window", "screen", "menu", "click",
        "experiment", "formula", "equation", "result", "reading",
    }
)

#: Real chemical-name words that sit one edit away from another real
#: chemical-name word (ethane/ethene, chloride/chlorate/chlorite,
#: sulphate/sulphite/sulphide, nitrate/nitrite). None of these belong in
#: `DOMAIN_VOCABULARY`, because spell-correction snaps *to* that set --
#: putting a confusable pair in it would let one be "corrected" into the
#: other. They are instead recognised and passed through untouched,
#: exactly like a formula, without ever being a correction target.
PROTECTED_CHEMICAL_WORDS: frozenset[str] = frozenset(
    {
        "ethane", "ethene", "ethyne", "methane", "methanol", "methanal",
        "chloride", "chlorate", "chlorite", "perchlorate",
        "sulphate", "sulphite", "sulphide", "sulfate", "sulfite", "sulfide",
        "nitrate", "nitrite", "nitride",
        "hydroxide", "oxide", "hydride",
        "acetate", "acetone", "acetic",
    }
)

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

#: Anything that looks like a chemical formula, ion, or an
#: alphanumeric technical identifier. Never spell-corrected.
#:
#: Covers CH4, O2, Ni2+, H2SO4, NaOH, 6-31G, def2-SVP, B3LYP, 5.0.4.
_CHEMICAL_RE = re.compile(
    r"""
    ^(?:
        [A-Za-z]{1,3}\d+[+-]?                 # CH4, O2, Ni2, Ni2+
      | (?:[A-Z][a-z]?\d*){2,}[+-]?           # NaOH, H2SO4, CH3COOC2H5
      | \d+-\d+[A-Za-z]+\*{0,2}               # 6-31G, 6-31G**
      | [A-Za-z]+\d+-[A-Za-z]+                # def2-SVP
      | [A-Za-z]\d[A-Za-z]{2,}\d*             # B3LYP
      | \d+(?:\.\d+)+                         # 5.0.4
      | [a-z]+\d+[a-z]*                       # exp07, ch4
    )$
    """,
    re.VERBOSE,
)

#: Order matters: the basis-set and version forms ("6-31G**", "5.0.4")
#: are matched before the bare-number alternative could split them.
_TOKEN_RE = re.compile(
    r"\d+-\d+[A-Za-z]+\*{0,2}"
    r"|\d+(?:\.\d+){2,}"
    r"|[A-Za-z]+(?:[+\-']?[A-Za-z0-9]+)*[+-]?"
    r"|\d+(?:\.\d+)?[+-]?"
)

#: "exp 7", "experiment 7", "exp-7", "exp7", "expt 07"
_EXPLICIT_EXPERIMENT_RE = re.compile(
    r"\b(?:exp|expt|ex|experiment)\s*[-.#]?\s*(\d{1,2})\b", re.IGNORECASE
)

#: Minimum length before a token is eligible for spell correction. Short
#: tokens have too many near neighbours to correct safely.
_MIN_CORRECTABLE_LEN = 4

#: How close a match must be. 0.82 corrects "orbitl"->"orbital" and
#: "gabdit"->"gabedit" while refusing "chlorate"->"chloride".
_CORRECTION_CUTOFF = 0.82


@dataclass(frozen=True)
class NormalizedQuery:
    """The result of normalising one student message."""

    raw: str
    text: str
    tokens: tuple[str, ...] = ()
    #: (original, replacement) for every change made, so a wrong
    #: normalisation is debuggable from the response rather than invisible.
    corrections: tuple[tuple[str, str], ...] = ()
    #: Experiment numbers the student named outright, e.g. "exp 7".
    explicit_experiments: tuple[str, ...] = ()
    #: "english" | "hinglish" | "mixed"
    language: str = "english"
    #: True when the message leans on prior turns ("this step", "that button").
    has_anaphora: bool = False
    flags: frozenset[str] = field(default_factory=frozenset)

    @property
    def hinglish(self) -> bool:
        return self.language in ("hinglish", "mixed")


#: Words that mean the question only makes sense against earlier turns.
_ANAPHORA_RE = re.compile(
    r"\b(?:this|that|these|those|it|previous|next|last|above|below|"
    r"again|same)\s+"
    r"(?:step|screen|window|button|option|page|one|part|menu|tab|file|"
    r"value|table|graph|figure|thing|stage)\b"
    r"|\b(?:previous|next|last)\s+(?:screen|step|page)\b"
    r"|\bafter\s+(?:this|that)\b"
    r"|\bwhat\s+(?:comes\s+)?(?:next|after)\b"
    # Noun-first order: "which screen comes next", "what step is after".
    r"|\b(?:screen|step|page|button|option|window|tab|part|stage)\b"
    r"[^.]{0,15}\b(?:comes?\s+)?(?:next|after)\b",
    re.IGNORECASE,
)


def normalize(text: str) -> NormalizedQuery:
    """Normalise one student message. Deterministic; calls no model."""
    raw = text or ""
    working = unicodedata.normalize("NFKC", raw).strip()

    explicit = tuple(
        f"exp{int(m):02d}" for m in _EXPLICIT_EXPERIMENT_RE.findall(working)
    )
    has_anaphora = bool(_ANAPHORA_RE.search(working))

    # Normalise the "exp 7" family to a single token before tokenising, so
    # the router sees one identifier rather than a word plus a number.
    working = _EXPLICIT_EXPERIMENT_RE.sub(
        lambda m: f" experiment exp{int(m.group(1)):02d} ", working
    )

    tokens = _TOKEN_RE.findall(working)

    out: list[str] = []
    corrections: list[tuple[str, str]] = []
    hinglish_hits = 0
    english_hits = 0

    for token in tokens:
        lowered = token.lower()

        # Chemical identifiers, version strings and lone scientific
        # symbols pass through untouched.
        if _is_chemical(token) or _is_symbol(token) or lowered in PROTECTED_CHEMICAL_WORDS:
            out.append(lowered)
            english_hits += 1
            continue

        if lowered in FILLER_WORDS:
            corrections.append((token, ""))
            continue

        if lowered in HINGLISH_FUNCTION_WORDS:
            replacement = HINGLISH_FUNCTION_WORDS[lowered]
            hinglish_hits += 1
            if replacement != lowered:
                corrections.append((token, replacement))
            out.extend(replacement.split())
            continue

        if lowered in SHORTHAND:
            replacement = SHORTHAND[lowered]
            corrections.append((token, replacement))
            out.extend(replacement.split())
            english_hits += 1
            continue

        if lowered in DOMAIN_VOCABULARY:
            out.append(lowered)
            english_hits += 1
            continue

        corrected = _spell_correct(lowered)
        if corrected != lowered:
            corrections.append((token, corrected))
            out.append(corrected)
            english_hits += 1
            continue

        out.append(lowered)
        english_hits += 1

    collapsed = _collapse_repeats(out)

    return NormalizedQuery(
        raw=raw,
        text=" ".join(collapsed),
        tokens=tuple(collapsed),
        corrections=tuple(corrections),
        explicit_experiments=tuple(dict.fromkeys(explicit)),
        language=_language(hinglish_hits, english_hits),
        has_anaphora=has_anaphora,
        flags=frozenset(_flags(raw, collapsed)),
    )


def _is_chemical(token: str) -> bool:
    """Whether this token must be protected from correction.

    Errs toward protecting. A missed correction costs a retrieval hit; a
    wrong correction silently answers a different question.
    """
    if any(ch.isdigit() for ch in token) or "+" in token or "-" in token:
        return bool(_CHEMICAL_RE.match(token))
    # All-caps short tokens are formulae or acronyms (NaOH, HOMO, DFT).
    return token.isupper() and 2 <= len(token) <= 8


def _is_symbol(token: str) -> bool:
    """A lone letter that means a physical quantity, not a typo."""
    return len(token) == 1 and token.lower() in SCIENTIFIC_SYMBOLS


def _spell_correct(token: str) -> str:
    if len(token) < _MIN_CORRECTABLE_LEN:
        return token
    matches = difflib.get_close_matches(
        token, DOMAIN_VOCABULARY, n=1, cutoff=_CORRECTION_CUTOFF
    )
    if not matches:
        return token
    candidate = matches[0]
    # Refuse to "correct" one real vocabulary term into another.
    if token in DOMAIN_VOCABULARY:
        return token
    # Refuse corrections that change the first letter: those are far more
    # often a different word than a typo.
    if candidate[0] != token[0]:
        return token
    return candidate


def _collapse_repeats(tokens: list[str]) -> list[str]:
    """Collapse "how how do i" -> "how do i". Students double words when
    they retype; the duplicate carries no extra meaning."""
    out: list[str] = []
    for token in tokens:
        if out and out[-1] == token:
            continue
        out.append(token)
    return out


def _language(hinglish_hits: int, english_hits: int) -> str:
    if hinglish_hits == 0:
        return "english"
    if english_hits == 0:
        return "hinglish"
    return "mixed" if english_hits > hinglish_hits else "hinglish"


def _flags(raw: str, tokens: list[str]) -> set[str]:
    flags: set[str] = set()
    if len(tokens) <= 2:
        flags.add("very_short")
    if not tokens:
        flags.add("empty")
    if raw.isupper() and len(raw) > 8:
        flags.add("shouting")
    if "?" not in raw and len(tokens) <= 4:
        flags.add("fragment")
    return flags
