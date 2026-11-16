"""Turns postings and their labels into chat examples for training and scoring.

Usage: python -I build_examples.py <postings.jsonl> <labels.jsonl> <prompt.txt> <out.jsonl>

Each row: id, split, system, user, assistant. The assistant text is the label in the shape the
model is asked for: the fields of prompt-v1 only, without the labeller's note and English names.
"""

import json
import sys


def answer(label):
    def entries(name):
        return [{"skills": e["skills"], "quote": e["quote"]} for e in label.get(name) or []]

    years = label.get("min_years")
    return {
        "required": entries("required"),
        "nice_to_have": entries("nice_to_have"),
        "stack": entries("stack"),
        "seniority": {"level": label["seniority"]["level"], "quote": label["seniority"].get("quote")},
        "min_years": years["years"] if years else None,
        "constraints": [{"kind": c["kind"], "value": c["value"], "hard": c["hard"], "quote": c["quote"]} for c in label.get("constraints") or []],
    }


def main():
    postings_path, labels_path, prompt_path, out_path = sys.argv[1:5]
    system = open(prompt_path, encoding="utf-8").read()
    labels = {json.loads(l)["id"]: json.loads(l) for l in open(labels_path, encoding="utf-8") if l.strip()}
    n = 0
    with open(out_path, "w", encoding="utf-8", newline="\n") as out:
        for line in open(postings_path, encoding="utf-8"):
            posting = json.loads(line)
            label = labels.get(posting["id"])
            if label is None:
                sys.exit(f"{posting['id']}: no label")
            row = {
                "id": posting["id"],
                "split": posting.get("split", "test"),
                "system": system,
                "user": f"TITLE: {posting['title']}\n{posting['description']}",
                "assistant": json.dumps(answer(label), ensure_ascii=False),
            }
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1
    print(f"{n} examples")


if __name__ == "__main__":
    main()
