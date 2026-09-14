# Category 1 — Known-correct worked examples

**Updated 2026-09-12.** The manual arrived, as IACHY102 (see
`manual/README.md` and `docs/final_audit.md` for the course-code
mismatch this uncovered). Of the 10 assessed experiments, exactly **one**
— Experiment 1 (Zn–Cu EMF thermodynamics) — has a fully worked numeric
example printed in the manual (p.13–15), and `exp01.json` transcribes it
verbatim. The other 9 experiments' manual sections either give no worked
example at all, or leave the observation tables blank for the student's
own run — see `manual/IACHY102_manual.md`'s summary table at the bottom
for the per-experiment breakdown. Those 9 stay absent from this
directory rather than getting fabricated ground truth.

Category 1 is defined by `docs/golden_dataset_plan.md` as values pulled
*directly and verbatim* from the manual's own solved sample calculations.

Fabricating plausible-looking chemistry here would be the worst available
option. A ground-truth file is the thing every Tier 1 test measures itself
against; if its numbers are invented, every test that passes against them
is measuring nothing, while *looking* like verified coverage. CLAUDE.md
("Testing philosophy") and AGENTS.md (`test-builder`) both say this
outright: a fabricated ground truth is worse than no test.

## What to do for the remaining 9 experiments, if a worked example ever surfaces

For each experiment that the manual gives a solved example for, add
`expNN.json` in this directory:

```json
{
  "experiment_id": "exp01",
  "manual_reference": "IACHY102 manual, section 1.4, p. 12",
  "inputs": { "standard_normality": 0.1, "standard_volume": 25.0 },
  "expected_output": 0.125,
  "expected_output_field": "normality_of_unknown",
  "transcribed_by": "<name>",
  "notes": ""
}
```

Rules for transcription, from the plan:

1. Copy the input values exactly as printed.
2. Copy the expected output exactly as printed. **Do not recompute and
   substitute your own number**, even if you think the manual's arithmetic
   could be derived differently — the point of this category is to match
   the manual, not to be independently correct. If the manual's own
   arithmetic looks wrong, transcribe it as printed and raise it with the
   professor separately.
3. Record the page/section so a reviewer can check the transcription.

`backend/tests/test_category1_worked_examples.py` picks these up
automatically. While this directory holds no `expNN.json` files, that test
skips with an explicit message naming the missing manual — it does not
silently pass.
