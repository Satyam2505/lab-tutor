# Experiment 7 (and the manual generally): image/screenshot handling — status

**Short answer: not implemented, and it cannot be implemented from what
currently exists in this repo.** This is a real, load-bearing gap for
Experiment 7 specifically, because its manual section (p.39-42) leans on
step-by-step UI screenshots (Gabedit's draw window, the ORCA input
generator dialog, the periodic-table picker, Avogadro's HOMO/LUMO
render) more than any other experiment's section does.

## What actually happened to the manual's images

The IACHY102 manual reached this repo by being pasted into a Claude Code
chat turn as document content (2026-09-12) — see `manual/README.md`. Each
page arrived as a rendered image *for the model to read in that turn*,
alongside OCR'd text. What got saved to the repo afterward was **only the
text**, transcribed by hand into `manual/IACHY102_manual.md`. The
page-image bytes themselves were never written to disk anywhere —
verified this session: there is no image file, no PDF, no cached asset
for this document anywhere under the repo or the session's scratch
directories. There was never a mechanism available to extract and save
them; reading a document in a chat turn does not hand the assistant a
saveable file.

Practically: `manual/IACHY102_manual.md`'s Experiment 7 section describes
*that* a screenshot exists at a given step ("Step 4: Optimize structure
and generate input file for Orca" etc.) because the surrounding
procedural text was transcribed, but the screenshot's actual pixels are
gone. A question like "which button do I press to open the ORCA input
generator" has no image for the system to ground an answer in, no matter
how good the retrieval or the LLM is.

## What this means for the golden dataset and evaluation

`evaluation/exp07_dataset.json` includes 4 cases tagged
`"category": "screenshot_reference"` with `"blocked_no_image_asset": true`
(e.g. "where exactly in Avogadro do I click to see the HOMO orbital
rendered"). `evaluation/run_evaluation.py` skips these explicitly rather
than running them and either (a) silently succeeding on a lucky generic
answer that happens to sound plausible, or (b) failing them and
miscounting that as a pipeline defect. They are marked, not answered,
not hidden, and not counted toward pass/fail rates.

## What would actually fix this

Two independent things, either one suffices to *start* fixing it:

1. **The real PDF becomes available.** `backend/rag/retrieval.py`
   already has a working PDF path (`pypdf` text extraction) alongside
   the new markdown path added this session. Extracting page *images*
   too would need a different library in the same module — `pypdf`
   gives text, not renders; `pdf2image` (needs Poppler) or `PyMuPDF`
   (`fitz`, no external binary) can rasterize each page. That is new,
   real engineering (a new ingestion path, a place to store the images,
   a way to serve them to the frontend and to a multimodal model), not
   a config change — flagged here as scoped-out, not attempted this
   session.
2. **Manually captured screenshots.** Someone actually running the
   Gabedit/ORCA/Avogadro workflow and saving the key screens as image
   files, uploaded into the repo (e.g. `manual/images/exp07/`). Cheaper
   than #1 for just Experiment 7, and arguably more useful than
   re-deriving screenshots from a PDF render, since it would capture the
   actual current UI rather than whatever version the original manual's
   screenshots happened to show.

Neither is possible without new input from outside this session — no
amount of pipeline engineering recovers image bytes that were never
saved. This is stated plainly here rather than worked around with a
generic "I can't show you a screenshot, but generally the button is
usually..." answer, which would be exactly the kind of unsupported claim
CLAUDE.md's grounding rules exist to prevent.

## Same gap, every other experiment

This is not Experiment-7-specific in cause, only in *impact* — Experiment
5 (ZnO XRD/SEM reference figures), Experiment 10 (Cu2O colour-swatch
table) and others also had figures in the manual that are equally
unsaved. Experiment 7 is where it's flagged first and hardest because
its procedure is the most UI-screenshot-dependent of the ten.
