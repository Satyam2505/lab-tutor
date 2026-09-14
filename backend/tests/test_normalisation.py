"""Normalisation must clarify intent without touching the science."""

from __future__ import annotations

import pytest

from backend.scope.normalize import DOMAIN_VOCABULARY, normalize


def n(text: str) -> str:
    return normalize(text).text


# ---------------------------------------------------------------------------
# The rule that matters: chemistry survives intact
# ---------------------------------------------------------------------------

#: Pairs that differ by roughly one edit and mean different things. A
#: spell-corrector that "helps" here has silently changed the question.
CONFUSABLE_CHEMISTRY = [
    "NO2", "NO3", "SO3", "SO4", "CH4", "CH3", "C2H4", "C2H6",
    "Ni2+", "Na+", "Cl-", "H2SO4", "HNO3", "NaOH", "KOH",
    "chloride", "chlorate", "chlorite", "sulphide", "sulphate",
    "nitrite", "nitrate", "ethane", "ethene", "methane", "methanol",
]


@pytest.mark.parametrize("term", CONFUSABLE_CHEMISTRY)
def test_chemical_identifiers_are_never_rewritten(term):
    result = n(f"what about {term} here")
    assert term.lower() in result, (
        f"{term!r} was altered during normalisation. Correcting one real "
        "chemical name into another answers a different question than the "
        "one asked."
    )


@pytest.mark.parametrize(
    "symbol", ["k", "n", "N", "V", "R", "T", "m", "x", "y"]
)
def test_lone_scientific_symbols_survive(symbol):
    assert symbol.lower() in n(f"what does {symbol} mean here").split()


def test_the_rate_constant_k_is_not_turned_into_chat_shorthand():
    """Regression: an earlier revision mapped "k" -> "ok", which turned
    experiment 2's rate constant into nothing at all."""
    assert "k" in n("ethyl acetate ka k kaise nikale").split()
    assert "ok" not in n("ethyl acetate ka k kaise nikale")


def test_basis_sets_and_versions_survive():
    assert "6-31g" in n("use 6-31G basis set")
    assert "b3lyp" in n("run with B3LYP functional")
    assert "5.0.4" in n("orca 5.0.4 version")


# ---------------------------------------------------------------------------
# Hinglish
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "must_contain"),
    [
        ("orca ka output kaha milega", ["orca", "output", "where"]),
        ("methane ka homo kaise dekhu", ["methane", "homo", "how"]),
        ("mera orca run nahi hora", ["orca", "run", "not"]),
        ("gabedit me option kidhar hai", ["gabedit", "option", "where"]),
        ("ni2 calibration graph kaise banega", ["ni2", "calibration", "how"]),
        ("exp 7 mein orca input kaha se banau", ["exp07", "orca", "where"]),
        ("yeh step kyun karna hai", ["this", "step", "why"]),
        ("kitne readings lene hai", ["how many", "reading"]),
    ],
)
def test_hinglish_question_words_map_to_english(raw, must_contain):
    result = n(raw)
    for token in must_contain:
        assert token in result, f"{token!r} missing from {result!r}"


def test_negation_is_preserved_not_dropped():
    """"my run is not happening" and "my run is happening" are opposite
    reports, and a normaliser that drops negation reports the wrong one."""
    assert "not" in n("mera orca run nahi hora")
    assert "not" not in n("mera orca run hora")


def test_hinglish_english_homographs_are_left_alone():
    """"is", "us", "to", "me" and "na" are Hindi particles and English
    words. Mapping them wrecks ordinary English."""
    assert n("tell me what is the next step") == "tell me what is the next step"
    assert "in" not in n("tell me about it").split()


def test_language_is_labelled():
    assert normalize("how do i get the final energy").language == "english"
    assert normalize("orca ka output kaha milega").hinglish
    assert normalize("ni2 calibration graph kaise banega").hinglish


# ---------------------------------------------------------------------------
# Typos, shorthand, filler
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("typo", "expected"),
    [
        ("orbitl", "orbital"),
        ("gabdit", "gabedit"),
        ("avagadro", "avogadro"),
        ("contributon", "contribution"),
        ("titrtion", "titration"),
        ("calibrtion", "calibration"),
        ("absorbace", "absorbance"),
        ("optimisaton", "optimisation"),
        ("cyclohexne", "cyclohexane"),
        ("conformaton", "conformation"),
    ],
)
def test_domain_typos_are_corrected(typo, expected):
    assert expected in n(f"where is the {typo} thing")


def test_correction_never_changes_the_first_letter():
    """A changed first letter is far more often a different word than a
    typo, and this is the cheapest guard against that class of error."""
    for word in ("bomo", "pethane", "sthane"):
        result = n(f"the {word} value")
        assert result.split()[1][0] == word[0]


def test_unknown_words_are_left_alone_rather_than_forced_into_vocabulary():
    assert "zxqwerty" in n("what is zxqwerty")


@pytest.mark.parametrize(
    ("raw", "expected_token"),
    [
        ("exp 7", "exp07"),
        ("expt 3", "exp03"),
        ("experiment 10", "exp10"),
        ("exp-8", "exp08"),
        ("exp7", "exp07"),
    ],
)
def test_experiment_references_normalise_to_one_identifier(raw, expected_token):
    result = normalize(f"how to do {raw}")
    assert expected_token in result.text
    assert expected_token in result.explicit_experiments


def test_filler_is_dropped_and_recorded():
    result = normalize("bhai plz gabedit kaise khole")
    assert "bhai" not in result.text
    assert "plz" not in result.text
    assert ("bhai", "") in result.corrections


def test_repeated_words_are_collapsed():
    assert n("how how do i i do this") == "how do i do this"


def test_shouting_and_fragments_are_flagged_not_altered():
    assert "shouting" in normalize("WHERE IS THE OUTPUT FILE").flags
    assert "fragment" in normalize("orca input").flags


def test_every_correction_is_recorded_for_debugging():
    """A wrong normalisation must be visible in the response rather than
    silently upstream of a confusing answer."""
    result = normalize("bhai orbitl contributon kaise nikale")
    changed = {before.lower() for before, _ in result.corrections}
    assert {"orbitl", "contributon", "bhai"} <= changed


def test_empty_input_is_handled():
    result = normalize("")
    assert result.text == ""
    assert "empty" in result.flags


# ---------------------------------------------------------------------------
# Anaphora
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "question",
    [
        "what comes after this step",
        "where is that button",
        "which screen comes next",
        "what do i do after this",
        "go back to the previous screen",
        "is it the same in that window",
    ],
)
def test_context_dependent_questions_are_flagged(question):
    assert normalize(question).has_anaphora


@pytest.mark.parametrize(
    "question",
    [
        "how do i create methane in gabedit",
        "where is the orca input generator",
        "what is normality",
    ],
)
def test_self_contained_questions_are_not_flagged_as_anaphoric(question):
    assert not normalize(question).has_anaphora


# ---------------------------------------------------------------------------
# Vocabulary hygiene
# ---------------------------------------------------------------------------


def test_vocabulary_contains_no_confusable_chemical_names():
    """Spell-correction snaps to this set, so a pair of near-identical
    chemical names inside it would let one be corrected into the other."""
    for bad in ("chloride", "chlorate", "nitrite", "nitrate", "sulphate", "sulphite"):
        assert bad not in DOMAIN_VOCABULARY


def test_vocabulary_has_no_short_entries_that_invite_bad_snaps():
    for term in DOMAIN_VOCABULARY:
        assert len(term) >= 4, f"{term!r} is short enough to attract wrong corrections"
