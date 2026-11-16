"""Tunes a small model on the labelled postings with LoRA.

Usage: python train_lora.py <model-dir> <examples.jsonl> <out-dir> [--epochs N] [--lr X] [--rank N]
                            [--max-tokens N] [--accumulate N] [--limit N] [--smoke]

Trains on the rows with split "train", measures the loss on "dev" after each epoch and saves the
adapter of each epoch under <out-dir>/epoch-N. The loss counts the answer only, never the prompt.
--smoke loads everything, runs two training steps and one dev step, and saves nothing.
"""

import json
import math
import random
import sys
import time
from pathlib import Path

import psutil
import torch
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer

TARGETS = r"^(?!.*(visual|vision)).*\.(q_proj|k_proj|v_proj|o_proj|gate_proj|up_proj|down_proj)$"


def option(name, default):
    return type(default)(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


def load_model(model_dir):
    # Straight onto the card: a copy in system memory first would cost 8 GB of RAM.
    try:
        return AutoModelForCausalLM.from_pretrained(model_dir, dtype=torch.bfloat16, device_map="cuda")
    except (ValueError, KeyError):
        from transformers import AutoModelForImageTextToText

        return AutoModelForImageTextToText.from_pretrained(model_dir, dtype=torch.bfloat16, device_map="cuda")


def encode(tok, row, end):
    prompt = tok.apply_chat_template(
        [{"role": "system", "content": row["system"]}, {"role": "user", "content": row["user"]}],
        add_generation_prompt=True, tokenize=False, enable_thinking=False,
    )
    prompt_ids = tok(prompt, add_special_tokens=False)["input_ids"]
    answer_ids = tok(row["assistant"] + end, add_special_tokens=False)["input_ids"]
    return prompt_ids, answer_ids


def main():
    model_dir, examples_path, out_dir = sys.argv[1], sys.argv[2], Path(sys.argv[3])
    epochs, lr, rank = option("--epochs", 3), option("--lr", 2e-4), option("--rank", 16)
    max_tokens, accumulate, limit = option("--max-tokens", 6000), option("--accumulate", 8), option("--limit", 0)
    smoke = "--smoke" in sys.argv
    torch.manual_seed(20261111)
    random.seed(20261111)

    tok = AutoTokenizer.from_pretrained(model_dir)
    end = "<|im_end|>" if "<|im_end|>" in tok.get_vocab() else tok.eos_token
    rows = [json.loads(l) for l in open(examples_path, encoding="utf-8")]
    data = {"train": [], "dev": []}
    too_long = 0
    for row in rows:
        if row["split"] not in data:
            continue
        prompt_ids, answer_ids = encode(tok, row, end)
        if len(prompt_ids) + len(answer_ids) > max_tokens:
            too_long += 1
            continue
        data[row["split"]].append((prompt_ids, answer_ids))
    if smoke:
        # The longest examples show the worst case for memory.
        data["train"].sort(key=lambda e: -(len(e[0]) + len(e[1])))
        data["dev"].sort(key=lambda e: -(len(e[0]) + len(e[1])))
    if limit:
        data["train"], data["dev"] = data["train"][:limit], data["dev"][: max(2, limit // 5)]
    sizes = sorted(len(p) + len(a) for p, a in data["train"])
    print(f"train {len(data['train'])}, dev {len(data['dev'])}, left out as too long {too_long}; tokens median {sizes[len(sizes) // 2]}, max {sizes[-1]}; end token {end!r}", flush=True)

    model = load_model(model_dir)
    model.config.use_cache = False
    model = get_peft_model(model, LoraConfig(r=rank, lora_alpha=2 * rank, lora_dropout=0.05, target_modules=TARGETS, task_type="CAUSAL_LM"))
    model.gradient_checkpointing_enable()
    model.enable_input_require_grads()
    model.to("cuda")
    trainable = [p for p in model.parameters() if p.requires_grad]
    print(f"trainable parameters {sum(p.numel() for p in trainable) / 1e6:.1f}M in {len(trainable)} tensors", flush=True)
    free, total = torch.cuda.mem_get_info()
    print(f"GPU memory after loading: {free / 2**30:.1f} GiB free of {total / 2**30:.1f}", flush=True)

    inner = model.get_base_model()
    backbone, head = inner.model, inner.lm_head

    def loss_of(example):
        prompt_ids, answer_ids = example
        ids = torch.tensor([prompt_ids + answer_ids], device="cuda")
        target = torch.tensor(answer_ids, device="cuda")
        with torch.autocast("cuda", dtype=torch.bfloat16):
            hidden = backbone(input_ids=ids).last_hidden_state
            # Only the answer is scored, so only its positions go through the vocabulary
            # layer: over the whole sequence that layer alone takes several GB.
            logits = head(hidden[0, len(prompt_ids) - 1:-1])
        return torch.nn.functional.cross_entropy(logits.float(), target)

    def dev_loss():
        model.eval()
        total = 0.0
        with torch.no_grad():
            for example in data["dev"]:
                total += loss_of(example).item()
        model.train()
        return total / max(1, len(data["dev"]))

    steps_per_epoch = math.ceil(len(data["train"]) / accumulate)
    total_steps = 2 if smoke else epochs * steps_per_epoch
    warmup = max(1, total_steps // 20)
    optimizer = torch.optim.AdamW(trainable, lr=lr, weight_decay=0.0)
    schedule = torch.optim.lr_scheduler.LambdaLR(
        optimizer, lambda s: (s + 1) / warmup if s < warmup else 0.5 * (1 + math.cos(math.pi * (s - warmup) / max(1, total_steps - warmup)))
    )
    if not smoke:
        out_dir.mkdir(parents=True, exist_ok=True)
    log = None if smoke else open(out_dir / "log.jsonl", "a", encoding="utf-8")

    def record(**fields):
        print(json.dumps(fields), flush=True)
        if log:
            log.write(json.dumps(fields) + "\n")
            log.flush()

    model.train()
    started, step = time.time(), 0
    last, paces, slow_run = time.time(), [], 0
    for epoch in range(1, epochs + 1):
        # Examples of similar length share a step, and the steps come in random order: the
        # allocator then reuses blocks of one size instead of keeping many sizes cached.
        by_length = sorted(range(len(data["train"])), key=lambda i: len(data["train"][i][0]) + len(data["train"][i][1]))
        groups = [by_length[i:i + accumulate] for i in range(0, len(by_length), accumulate)]
        random.shuffle(groups)
        order = [i for group in groups for i in group]
        running, counted = 0.0, 0
        for n, index in enumerate(order, 1):
            loss = loss_of(data["train"][index])
            (loss / accumulate).backward()
            running += loss.item()
            counted += 1
            del loss
            torch.cuda.empty_cache()
            # Spilling into system memory makes training ten times slower and starves the PC.
            # It shows as time per token: stop when that is far above what this run has seen.
            tokens = len(data["train"][index][0]) + len(data["train"][index][1])
            pace = (time.time() - last) / tokens
            last = time.time()
            typical = sorted(paces)[len(paces) // 2] if len(paces) >= 24 else None
            paces.append(pace)
            # One slow example is a hiccup of the PC; a spill keeps every example slow.
            slow_run = slow_run + 1 if typical and pace > 5 * typical else 0
            reason = None
            if slow_run >= 4:
                reason = f"four examples in a row took over 5 times the usual time per token (last {pace / typical:.0f} times)"
            elif psutil.virtual_memory().available < 2 * 2**30:
                reason = "under 2 GB of system memory free"
            if reason:
                record(stopped=reason, epoch=epoch, step=step)
                if not smoke:
                    model.save_pretrained(out_dir / "interrupted")
                sys.exit(3)
            if n % accumulate == 0 or n == len(order):
                torch.nn.utils.clip_grad_norm_(trainable, 1.0)
                optimizer.step()
                schedule.step()
                optimizer.zero_grad(set_to_none=True)
                step += 1
                if step % 5 == 0 or smoke:
                    record(epoch=epoch, step=step, of=total_steps, train_loss=round(running / counted, 4), minutes=round((time.time() - started) / 60, 1), peak_gib=round(torch.cuda.max_memory_allocated() / 2**30, 1), ram_free_gib=round(psutil.virtual_memory().available / 2**30, 1))
                    running, counted = 0.0, 0
                if smoke and step >= 2:
                    record(smoke_dev_loss=round(loss_of(data["dev"][0]).item(), 4))
                    print("smoke test passed", flush=True)
                    return
        model.save_pretrained(out_dir / f"epoch-{epoch}")
        record(epoch=epoch, dev_loss=round(dev_loss(), 4), minutes=round((time.time() - started) / 60, 1))
        last = time.time()
    print("training finished", flush=True)


if __name__ == "__main__":
    main()
