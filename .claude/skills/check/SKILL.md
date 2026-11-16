---
name: check
description: Run what CI runs on this repository (compile, tests, the data and privacy guard) before a PR
---
Run the steps in order from the repository root and stop at the first failure. Report each
step's result in one line; on a failure, show the error text and fix it before re-running.

```bash
python -m py_compile tools/*.py tests/*.py
python -m unittest discover -s tests -v
python tools/check_repo.py
```

`check_repo.py` looks at every file git tracks or would add and accepts only the kinds listed in
its `ALLOWED`: a finding means data, weights, a machine path or an e-mail address is about to be
committed. Never silence it by ignoring the file; move the file out of the repository. Nothing here needs a model, a graphics card or the
network: do not run `train_lora.py`, `run_hf.py` or `run_model.py` as part of the check.
