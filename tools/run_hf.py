"""Labels postings with a model loaded in PyTorch, with or without a tuned adapter.

Usage: python run_hf.py <model-dir> <examples.jsonl> <out.jsonl> [--adapter DIR] [--split NAME]
                        [--max-new-tokens N] [--limit N]

Reads the examples of build_examples.py (the same prompt the model was tuned with), answers
each one greedily and writes one label-shaped JSON line per posting, or "error". Answered ids
are skipped, so a run can be resumed.
"""

import json
import sys
import time

import psutil
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


def parse(text):
    """Reads the answer as JSON, allowing a code fence or words around the object."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object")
    label = json.loads(text[start:end + 1])
    if not isinstance(label, dict):
        raise ValueError("not a JSON object")
    return label


def option(name, default):
    return type(default)(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


def main():
    model_dir, examples_path, out_path = sys.argv[1:4]
    adapter, split = option("--adapter", ""), option("--split", "")
    max_new, limit = option("--max-new-tokens", 3000), option("--limit", 0)
    tok = AutoTokenizer.from_pretrained(model_dir)
    try:
        model = AutoModelForCausalLM.from_pretrained(model_dir, dtype=torch.bfloat16)
    except (ValueError, KeyError):
        from transformers import AutoModelForImageTextToText

        model = AutoModelForImageTextToText.from_pretrained(model_dir, dtype=torch.bfloat16)
    if adapter:
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, adapter).merge_and_unload()
    model.to("cuda").eval()
    end_ids = [i for i in (tok.convert_tokens_to_ids("<|im_end|>"), tok.eos_token_id) if isinstance(i, int) and i >= 0]

    rows = [json.loads(l) for l in open(examples_path, encoding="utf-8")]
    if split:
        rows = [r for r in rows if r["split"] == split]
    done = set()
    try:
        for line in open(out_path, encoding="utf-8"):
            row = json.loads(line)
            if not row.get("error"):
                done.add(row["id"])
    except FileNotFoundError:
        pass
    todo = [r for r in rows if r["id"] not in done]
    if limit:
        todo = todo[:limit]
    ok = errors = 0
    with open(out_path, "a", encoding="utf-8", newline="\n") as out:
        for row in todo:
            prompt = tok.apply_chat_template(
                [{"role": "system", "content": row["system"]}, {"role": "user", "content": row["user"]}],
                add_generation_prompt=True, tokenize=False, enable_thinking=False,
            )
            ids = tok(prompt, add_special_tokens=False, return_tensors="pt")["input_ids"].to("cuda")
            started = time.time()
            with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16):
                generated = model.generate(ids, max_new_tokens=max_new, do_sample=False, eos_token_id=end_ids, pad_token_id=end_ids[0])
            new = generated[0, ids.shape[1]:]
            text = tok.decode(new, skip_special_tokens=True).strip()
            meta = {"seconds": round(time.time() - started, 1), "prompt_tokens": ids.shape[1], "completion_tokens": int(new.shape[0])}
            try:
                label = parse(text)
                # The posting's id last: the answer is untrusted and may hold an "id".
                result = {**label, "id": row["id"], "_run": meta}
                ok += 1
            except ValueError as err:
                result = {"id": row["id"], "error": f"not usable JSON ({err})", "raw": text[:300], "_run": meta}
                errors += 1
            out.write(json.dumps(result, ensure_ascii=False) + "\n")
            out.flush()
            del generated, ids
            torch.cuda.empty_cache()
            # A run that spills into system memory crawls and starves the PC: stop instead.
            if psutil.virtual_memory().available < 6 * 2**30:
                print(f"stopped early: under 6 GB of system memory free after {ok + errors} postings")
                break
    print(f"asked {len(todo)}, ok {ok}, errors {errors}, skipped {len(done)}")


if __name__ == "__main__":
    main()
