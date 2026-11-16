# Job-posting skill extraction

A small model that reads a job posting and says what the employer asks of the candidate: which
skills are required, which are a bonus, the seniority, the years of experience, and conditions
such as language or work permit. Each item comes with a quote from the posting, so the answer
can be checked by a program.

This repository holds the labelling rules, the tools and the results of tuning a 4-billion-
parameter open model for that task on one consumer graphics card.

| 200 test postings | Keyword rules | 26B model, untuned | 4B model, untuned | 4B model, tuned |
|---|---|---|---|---|
| Required skills found | 21% | 75% | 71% | **89%** |
| Reported skills that are asked for | 77% | 81% | 66% | **87%** |
| Required filed as required (F1) | none | 0.75 | 0.59 | **0.85** |

Full tables, method and limits: [RESULTS.md](RESULTS.md). The tuned adapter:
[MODEL_CARD.md](MODEL_CARD.md).

## What is here

| Path | Holds |
|---|---|
| `LABELS.md` | The label format and the rules for labelling a posting. |
| `tools/prompt-v1.txt` | The prompt every model was given. |
| `tools/sample_testset.py`, `sample_trainset.py` | Draw a test set, then training and development postings from other companies. |
| `tools/split_batches.py`, `labeller-brief.md` | Split postings into batches and brief a labeller. |
| `tools/verify_labels.py` | Check that every quote and skill of a label is in its posting. |
| `tools/merge_labels.py`, `find_brackets.py`, `apply_patches.py` | Merge label batches and apply a targeted repair. |
| `tools/build_examples.py`, `train_lora.py` | Build chat examples and train the adapter. |
| `tools/run_hf.py`, `run_model.py` | Label postings with a model in PyTorch, or through a local chat-completions server. |
| `tools/score.py` | Score a run against labels. |
| `tools/check_repo.py` | Fail when data, weights or machine-specific text is about to be committed. |
| `tests/` | Tests of the tools, on invented postings. |

## What is not here, and why

**No posting text and no labels.** The postings belong to the employers that wrote them, and
every label quotes them word for word. The sets used here (200 test, 500 training and 100
development postings) were fetched from public job boards and public career pages and stay
outside the repository. `tools/check_repo.py` and CI keep it that way.

**No fetcher.** The postings were fetched and turned into plain text by the application this
work was done for. The tools start from a `postings.jsonl` with one JSON object per line:

```json
{"provider": "board name", "external_id": "id at the source", "company": "Example GmbH", "title": "Senior Backend Engineer", "location": "Berlin", "description": "plain text, paragraphs separated by blank lines", "url": "https://..."}
```

## Reproduce the steps

```bash
# 1. Draw the test set, then training and development postings from other companies.
python -I tools/sample_testset.py pool.jsonl data/test
python -I tools/sample_trainset.py data/test data/train pool2.jsonl

# 2. Label each set (shown for data/train; data/test is labelled the same way).
python -I tools/split_batches.py data/train/postings.jsonl - data/train/work 25
#    ... a labeller writes data/train/labels/batch-NN.jsonl, following tools/labeller-brief.md ...
python -I tools/verify_labels.py data/train/postings.jsonl data/train/labels/batch-01.jsonl
python -I tools/merge_labels.py data/train/postings.jsonl data/train/labels.jsonl data/train/labels/batch-*.jsonl

# 3. Build the examples and train.
python -I tools/build_examples.py data/train/postings.jsonl data/train/labels.jsonl tools/prompt-v1.txt data/examples-train.jsonl
python -I tools/build_examples.py data/test/postings.jsonl data/test/labels.jsonl tools/prompt-v1.txt data/examples-test.jsonl
python tools/train_lora.py <base-model-dir> data/examples-train.jsonl runs/v2 --epochs 3 --max-tokens 4100

# 4. Choose a pass on the development postings (the rows with "split": "dev").
python tools/run_hf.py <base-model-dir> data/examples-train.jsonl runs/dev-v2-epoch3.jsonl --adapter runs/v2/epoch-3 --split dev
python -I tools/score.py score data/train/postings.jsonl data/train/labels.jsonl runs/dev-v2-epoch3.jsonl - --split dev

# 5. Score the test set once, tuned and untuned.
python tools/run_hf.py <base-model-dir> data/examples-test.jsonl runs/test-v2-epoch3.jsonl --adapter runs/v2/epoch-3
python tools/run_hf.py <base-model-dir> data/examples-test.jsonl runs/test-untuned.jsonl
python -I tools/score.py score data/test/postings.jsonl data/test/labels.jsonl runs/test-v2-epoch3.jsonl -
```

`sample_testset.py` and `sample_trainset.py` read the `provider` field: `greenhouse`, `lever`,
`ashby` and `smartrecruiters` are taken as one employer's own career board, any other value as
an aggregator that lists many employers. The last argument of `score.py score` is an optional
alias map (`-` for none); `score.py strings` lists the skill names to build one from.

The sampling, checking and scoring tools need only Python 3.12. Training and `run_hf.py` need
`torch`, `transformers`, `peft`, `accelerate` and `psutil`, and a graphics card with about
16 GB of memory.

## Checks

```bash
python -m unittest discover -s tests -v
python tools/check_repo.py
```

## Licence

The code and documents are under the [MIT License](LICENSE). The adapter is a derivative of
Qwen3.5-4B and is released under the Apache License 2.0, like its base model.
