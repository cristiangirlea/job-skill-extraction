# Results

Every score below is printed by `tools/score.py` for the run named under its table. Skills are
micro-averaged over postings; two skill names match as the script's docstring describes. One run
per system, greedy decoding. A posting without a usable answer counts as wrong on every row.

## Test set

200 postings from 116 companies, none of which appears in the training data. The tuned model was
chosen on the development set first and scored here once.

| 200 test postings | Keyword rules | 26B model, untuned | Qwen3.5-4B, untuned | Qwen3.5-4B, tuned |
|---|---|---|---|---|
| Required skills found (recall) | 0.21 | 0.75 | 0.71 | **0.89** |
| Reported skills that the posting asks for (precision) | 0.77 | 0.81 | 0.66 | **0.87** |
| The two combined (F1) | 0.33 | 0.78 | 0.68 | **0.88** |
| Required skills filed as required (F1) | no such notion | 0.75 | 0.59 | **0.85** |
| Nice-to-have skills filed as nice to have (F1) | no such notion | 0.81 | 0.68 | **0.88** |
| Seniority level right | 0.55 | 0.93 | 0.88 | **0.97** |
| Years of experience right | not read | 0.99 | 0.96 | 0.98 |
| Hard constraints, precision / recall | not comparable | 0.71 / 0.84 | 0.47 / 0.66 | **0.91** / 0.83 |
| Postings with an eligibility condition caught (of 17) | 5 | 14 | 15 | 13 |
| Required languages caught | 1 of 32 (not English) | 0.93 | 0.62 | **0.96** |
| Quotes copied exactly | no quotes | 0.985 | 0.95 | **0.995** |
| Unusable answers (of 200) | none | none | 6 | 1 |
| Seconds per posting (median) | instant | 22 | 25 | 17 |

Required skills found by the tuned model, by the language guess of the sampler: German 0.89,
everything else (almost all English) 0.89.

| Column | Run | How it was produced |
|---|---|---|
| Keyword rules | `test-rules.jsonl` | The vocabulary matcher of the job-search application this work was done for. It knows technology names only, cannot tell required from nice to have, and reads the highest level word anywhere in the text as the seniority. |
| 26B model, untuned | `test-26b-untuned.jsonl` | A general open-weight model of about 26 billion parameters, 4-bit quantised, served by llama.cpp through `tools/run_model.py`, with the answer forced into the JSON schema. |
| Qwen3.5-4B, untuned | `test-untuned.jsonl` | `tools/run_hf.py` without an adapter: PyTorch, bf16, no schema. |
| Qwen3.5-4B, tuned | `test-v2-epoch3.jsonl` | `tools/run_hf.py --adapter` with pass 3 of training run v2, the adapter of `MODEL_CARD.md`. Same card and settings as the untuned run. |

- All three models got the same prompt, `tools/prompt-v1.txt`.
- "Seniority level right" is `seniority.label_right` for the models and
  `seniority.level_number_right` for the keyword rules, which give a level number only (lead,
  staff and manager share one number).
- "Seconds per posting" is the median of the run files' own timing, not a score.
- The run files are not published: every answer in them quotes the postings.

## Development set

100 postings from 54 companies, split off from the training postings by company. Used to choose
between the passes of the training run.

| 100 development postings | Untuned | Pass 1 | Pass 2 | Pass 3 (chosen) |
|---|---|---|---|---|
| Required skills found (recall) | 0.67 | 0.72 | 0.78 | 0.83 |
| Reported skills that the posting asks for (precision) | 0.68 | 0.93 | 0.91 | 0.90 |
| The two combined (F1) | 0.67 | 0.81 | 0.84 | 0.86 |
| Required skills filed as required (F1) | 0.59 | 0.79 | 0.81 | 0.83 |
| Hard constraints, precision / recall | 0.51 / 0.62 | 0.91 / 0.86 | 0.92 / 0.83 | 0.92 / 0.84 |
| Seniority level right | 0.82 | 0.95 | 0.94 | 0.93 |
| Unusable answers (of 100) | 2 | 0 | 1 | 2 |

Runs: `dev-untuned.jsonl`, `dev-v1-epoch1.jsonl`, `dev-v2-epoch2.jsonl`, `dev-v2-epoch3.jsonl`,
all through `tools/run_hf.py`. Pass 1 is an earlier training run (v1) of one pass over slightly
fewer postings; passes 2 and 3 are from the final run (v2). The first pass taught the model what
to leave out; the later passes taught it to find more of what belongs.

## The adapter in llama.cpp

The adapter of pass 3 converted to GGUF (float32) and applied at run time to a 4-bit GGUF of the
base model, against the same adapter on the full-precision base in PyTorch. Scored on the
development set, not on the test set.

| 100 development postings | PyTorch, full precision | llama.cpp, 4-bit base + adapter |
|---|---|---|
| Required skills found (recall) | 0.83 | 0.86 |
| Reported skills that the posting asks for (precision) | 0.90 | 0.89 |
| The two combined (F1) | 0.86 | 0.88 |
| Required skills filed as required (F1) | 0.83 | 0.84 |
| Hard constraints, precision / recall | 0.92 / 0.84 | 0.90 / 0.85 |
| Postings with an eligibility condition caught (of 9) | 8 | 7 |
| Seniority level right | 0.93 | 0.96 |
| Quotes copied exactly | 0.997 | 0.997 |
| Unusable answers (of 100) | 2 | 0 |
| Seconds per posting (median) | 17 | 10 |

| Column | Run | How it was produced |
|---|---|---|
| PyTorch, full precision | `dev-v2-epoch3.jsonl` | The "Pass 3" run of the table above: `tools/run_hf.py --adapter`, bf16, no schema. |
| llama.cpp, 4-bit base + adapter | `dev-gguf-q4km-lora.jsonl` | `convert_lora_to_gguf.py` of llama.cpp build b11321 with `--outtype f32`; `llama-server` of the same build with a Q4_K_M GGUF of Qwen3.5-4B and `--lora`; `tools/run_model.py`, four requests at a time, thinking off, with the answer forced into the JSON schema. |

- Both columns were scored without an alias map (`-` as the last argument of `score.py score`).
  For the PyTorch run that gives the same rounded figures as the table above.
- The two runs differ in three things at once: the base model's precision, the runtime, and the
  schema. Both unusable answers of the PyTorch run are invalid JSON by the run file's error
  field, which the schema rules out, and an unusable answer counts as wrong on every row. The
  remaining differences are too small to rank the two setups on 100 postings.
- "Seconds per posting" is the median of the run files' own timing, not a score, on the same
  20 GB consumer graphics card. The PyTorch run answered one posting at a time; the llama.cpp
  run had four requests in flight, each timed on its own, so the 100 postings took less time
  in total than the median suggests.

## What the numbers do not show

- **The labels are a model's, not people's.** A large language model labelled every posting
  from the written rules in `LABELS.md`. A script confirmed that each quote and skill is in the
  posting; a few dozen labels were compared with their postings by hand. Agreement with these
  labels is not the same as being right.
- **No ceiling.** How far two careful labellers agree on these postings was not measured.
- **Rules moved.** The test set was labelled before changes 9 to 17 of `LABELS.md`; the training
  set, in part, after them. Some of the tuned model's remaining errors on the test set are the
  newer convention.
- **Noise.** One run per system on 200 postings: differences of two or three points mean little.
- **Reproducing.** The posting text is not published (see `README.md`). The scores above used an
  alias map built from a private vocabulary, which affects the skill rows only. Measured for the
  tuned column alone: without the map, required skills found is 0.890 instead of 0.892 and
  precision 0.866 instead of 0.868. The other columns were not rescored without it; the keyword
  rules' column depends on it most.
- **Eligibility.** The tuned model caught fewer eligibility conditions (citizenship, work
  permit, clearance) than the untuned one. Keep a separate check for those.
- **Languages.** Most postings are English and some are German; a few are Dutch or French, and
  the sampler's language guess counts those as English.
