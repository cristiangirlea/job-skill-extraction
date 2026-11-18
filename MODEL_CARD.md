# Model card: job-posting skill extraction (LoRA adapter)

## What it is

A LoRA adapter for [Qwen/Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B) that reads one job
posting (title and description as plain text, mostly English and German) and returns JSON: the skills
the posting requires, the skills it marks as a bonus, the technologies it names as the team's
stack, the seniority level, the years of experience asked, and conditions on the candidate
(language, location, work permit, degree and so on). Every item carries a quote from the posting,
so a program can check that the answer is grounded in the text.

- **Base model:** Qwen3.5-4B, Apache License 2.0. This adapter is a derivative of it and is
  released under the same licence.
- **Adapter:** LoRA rank 16, alpha 32, dropout 0.05, on the attention and feed-forward
  projections of the language layers (21.2 million trained parameters, 85 MB, as the training
  log and the file report).
- **Prompt:** `tools/prompt-v1.txt` as the system message, then `TITLE: <title>` and the
  description as the user message, with thinking turned off in the chat template.

## Use

The files are attached to the
[adapter-v1 release](https://github.com/cristiangirlea/job-skill-extraction/releases/tag/adapter-v1):
put `adapter_model.safetensors` and `adapter_config.json` in one folder. Load the base model with
`transformers`, attach the adapter from that folder with `peft`, and send the prompt above;
`tools/run_hf.py` does exactly that with `--adapter <folder>`. Serve it with a JSON schema where the runtime
supports one: without it about 1 answer in 100 is not valid JSON (an unescaped quotation mark
copied from the posting).

For llama.cpp the release also holds the adapter as GGUF,
`job-skill-extraction-qwen3.5-4b-lora-f32.gguf`. Start the server with a GGUF of the base model
and the adapter on top, then send requests as `tools/run_model.py` does (the JSON schema, and
thinking turned off):

```bash
llama-server -m <Qwen3.5-4B GGUF> --lora job-skill-extraction-qwen3.5-4b-lora-f32.gguf --host 127.0.0.1 --port 8081
```

On the development postings this setup, with a 4-bit base, scored like the full-precision
model in PyTorch (`RESULTS.md`, "The adapter in llama.cpp").

Intended for ranking and filtering job postings for a job seeker. It is not a hiring tool and
must not be used to assess people.

## Training

- **Data:** 493 job postings (those under 4,100 tokens of 500) from public job boards and public
  employer career pages, with labels written by a large language model following `LABELS.md`.
  A script verified every quoted span against its posting. None of the postings, and nothing
  else in the training data, comes from any person's profile, CV or applications.
- **Procedure:** three passes, learning rate 2e-4 with a cosine schedule, eight examples per
  step, loss on the answer only. 89 minutes on one 20 GB consumer graphics card, by the
  training log.
- **Selection:** the third pass, chosen on 100 development postings from other companies.

## Evaluation

On 200 test postings from 116 companies outside the training data, scored by `tools/score.py`
(runs `test-untuned.jsonl` and `test-v2-epoch3.jsonl`; details and limits in `RESULTS.md`):

| | Untuned base | This adapter |
|---|---|---|
| Required skills found | 0.71 | 0.89 |
| Reported skills that the posting asks for | 0.66 | 0.87 |
| Required skills filed as required (F1) | 0.59 | 0.85 |
| Seniority level right | 0.88 | 0.97 |
| Hard constraints, precision / recall | 0.47 / 0.66 | 0.91 / 0.83 |

## Limits and risks

- The labels it learned from are a model's reading of written rules, not human annotation.
- It catches fewer eligibility conditions (citizenship, work permit, clearance) than the untuned
  model: 13 of 17 postings against 15. Do not rely on it alone for those.
- Trained and tested on software and IT postings, mostly in English and German with a few in
  Dutch and French, mostly from Europe and North America. Other fields and languages are
  untested, and the few Dutch and French postings were not scored separately.
- Job postings sometimes contain a recruiter's name or contact details, and some were in the
  training text. The adapter is trained to copy spans from its input, not to recall training
  text, but it has not been tested for memorisation.
- Posting text is untrusted input. The prompt tells the model to treat it as data; that is not
  a security boundary.
