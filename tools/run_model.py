"""Asks a local model server (chat-completions API) to label postings.

Usage: python -I run_model.py <postings.jsonl> <prompt.txt> <out.jsonl> [--url URL] [--workers N] [--limit N] [--max-tokens N]

One JSON line per posting in <out.jsonl>: the model's label with "id", or "error".
Postings already answered without an error are skipped, so a run can be resumed.
Only the loopback server is called; nothing leaves this computer.
"""

import json
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

LEVELS = ["intern", "junior", "mid", "senior", "lead", "staff", "principal", "manager", "director", "unspecified"]
KINDS = ["citizenship", "work_authorization", "clearance", "language", "location", "timezone", "travel", "degree", "certification", "contract", "other"]
ENTRY = {
    "type": "object",
    "properties": {"skills": {"type": "array", "items": {"type": "string"}, "minItems": 1}, "quote": {"type": "string"}},
    "required": ["skills", "quote"],
    "additionalProperties": False,
}
SCHEMA = {
    "type": "object",
    "properties": {
        "required": {"type": "array", "items": ENTRY},
        "nice_to_have": {"type": "array", "items": ENTRY},
        "stack": {"type": "array", "items": ENTRY},
        "seniority": {
            "type": "object",
            "properties": {"level": {"type": "string", "enum": LEVELS}, "quote": {"type": ["string", "null"]}},
            "required": ["level", "quote"],
            "additionalProperties": False,
        },
        "min_years": {"type": ["integer", "null"]},
        "constraints": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": KINDS},
                    "value": {"type": "string"},
                    "hard": {"type": "boolean"},
                    "quote": {"type": "string"},
                },
                "required": ["kind", "value", "hard", "quote"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["required", "nice_to_have", "stack", "seniority", "min_years", "constraints"],
    "additionalProperties": False,
}


def loopback(url):
    """True when the URL names this computer and nothing else."""
    try:
        parts = urllib.parse.urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    return parts.scheme == "http" and parts.hostname in {"127.0.0.1", "localhost", "::1"} and parts.username is None and parts.password is None and port is not None


def option(name, default):
    return type(default)(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


def ask(url, system, posting, max_tokens):
    body = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": f"TITLE: {posting['title']}\n{posting['description']}"},
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
        # Without this a thinking model can spend the whole budget before the answer.
        "chat_template_kwargs": {"enable_thinking": False},
        "response_format": {"type": "json_schema", "json_schema": {"name": "label", "strict": True, "schema": SCHEMA}},
    }
    request = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"})
    started = time.time()
    try:
        with urllib.request.urlopen(request, timeout=900) as response:
            answer = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        return {"error": f"HTTP {err.code}: {err.read().decode('utf-8', 'replace')[:300]}"}
    except Exception as err:  # a timeout or a dropped connection is recorded, and the run goes on
        return {"error": f"{type(err).__name__}: {err}"}
    choice = answer["choices"][0]
    text = choice["message"].get("content") or ""
    usage = answer.get("usage") or {}
    meta = {"seconds": round(time.time() - started, 1), "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"), "finish": choice.get("finish_reason")}
    try:
        label = json.loads(text)
    except json.JSONDecodeError as err:
        return {"error": f"not JSON ({err})", "raw": text[:400], "_run": meta}
    if not isinstance(label, dict):
        return {"error": "not a JSON object", "raw": text[:400], "_run": meta}
    label["_run"] = meta
    return label


def main():
    postings_path, prompt_path, out_path = sys.argv[1:4]
    url = option("--url", "http://127.0.0.1:8081/v1/chat/completions")
    if not loopback(url):
        sys.exit("only a loopback server is allowed")
    workers, limit, max_tokens = option("--workers", 3), option("--limit", 0), option("--max-tokens", 3500)
    system = open(prompt_path, encoding="utf-8").read()
    postings = [json.loads(line) for line in open(postings_path, encoding="utf-8")]
    done = set()
    try:
        for line in open(out_path, encoding="utf-8"):
            row = json.loads(line)
            if not row.get("error"):
                done.add(row["id"])
    except FileNotFoundError:
        pass
    todo = [p for p in postings if p["id"] not in done]
    if limit:
        todo = todo[:limit]
    lock = threading.Lock()
    counts = {"ok": 0, "error": 0}
    with open(out_path, "a", encoding="utf-8", newline="\n") as out:
        def work(posting):
            row = ask(url, system, posting, max_tokens)
            row = {**row, "id": posting["id"]}
            with lock:
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
                out.flush()
                counts["error" if row.get("error") else "ok"] += 1
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(work, todo))
    print(f"asked {len(todo)}, ok {counts['ok']}, errors {counts['error']}, skipped {len(done)}")


if __name__ == "__main__":
    main()
