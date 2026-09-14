# knowledge/adjacent/

**This directory is Tier C: curated supplementary material, NOT the
IACHY102 manual.** See `backend/sources/tiers.py` for the full
hierarchy and `docs/source_manifest.json` (`adjacent_knowledge_v1`) for
how it is registered.

## What this is for

Level 2 ("adjacent") questions per the Phase 1 brief: a student asking
something meaningfully related to an experiment that the manual itself
does not cover -- broader theory, general software troubleshooting,
background concepts. Examples the brief gives directly: "why does DFT
work physically?", general ORCA troubleshooting, general basis-set
concepts, torsional strain, integrated rate laws, Beer-Lambert theory,
camera colour science.

## What this is not for

- **Never** a substitute for the manual's own procedure, formula,
  numbering, table, or expected value. `backend/sources/tiers.py`
  enforces this structurally: `Usage.EXPERIMENT_INSTRUCTION` does not
  permit `SourceTier.CURATED_ADJACENT` as a source at all, so a direct
  procedural question cannot be answered from this directory even if a
  file here happens to cover it.
- **Never** presented to a student without the supplementary label.
  `AnswerStatus.ADJACENT_SUPPORTED.requires_supplementary_label` is
  `True`, and `backend/retrieval/pipeline.py::_validate` asserts every
  answer built from this tier carries it.
- Not a place to transcribe manual content "so retrieval has more to
  work with". If a file here starts explaining the specific steps of an
  IACHY102 procedure, it has become a stand-in for the manual and no
  longer belongs at this tier — remove it or fold it into a real Tier A/B
  ingestion instead once the manual exists.

## Content policy

Everything in this directory is general chemistry/software knowledge
that is standard enough to appear in an undergraduate textbook or public
software documentation for the tool in question — it does not encode
IACHY102-specific wording, tables, tolerances, or exact required steps
(those must come from the manual once it is available; see
`docs/current_state_audit.md` §0). Each file is scoped to one topic and
tagged in its front-matter comment with the experiment(s) it supports.

## Files

| File | Experiment(s) | Covers |
| --- | --- | --- |
| `exp07_molecular_orbital_theory.md` | exp07 | HOMO/LUMO, MO theory basics, why basis sets and functionals matter |
| `exp07_orca_troubleshooting.md` | exp07 | General computational-chemistry job failure modes (not manual-specific) |
| `exp08_conformational_analysis_theory.md` | exp08 | Torsional strain, steric effects, Newman projections, energy landscapes |
| `exp02_reaction_kinetics_theory.md` | exp02 | Integrated rate laws, pseudo-order kinetics, Arrhenius, catalysis |
| `exp03_beer_lambert_and_color_science.md` | exp03 | Beer-Lambert derivation, camera colour science, RGB method limitations |

Ingestion reads every `.md`/`.txt` file directly under this directory
(`backend/retrieval/ingest.py::_extract_from_directory`); there is no
recursion into subdirectories, so a new topic file just needs to be
added here and it is picked up on the next ingestion run.
