"""Merges the pilot labels and the batch files into one file and prints what it holds.

Usage: python -I merge_labels.py <postings.jsonl> <out-labels.jsonl> <label-file> ... [--replace <label-file> ...]

Labels in a file after --replace take the place of earlier ones (a second pass).

Exit code 1 when a posting has no label, has two, or a label names no posting.
"""

import collections
import json
import statistics
import sys

sys.stdout.reconfigure(encoding="utf-8")
ids = [json.loads(line)["id"] for line in open(sys.argv[1], encoding="utf-8")]
labels = {}
problems = []
replacing = False
replaced = 0
for path in sys.argv[3:]:
    if path == "--replace":
        replacing = True
        continue
    for n, line in enumerate(open(path, encoding="utf-8"), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as err:
            problems.append(f"{path} line {n}: not JSON ({err})")
            continue
        if row.get("id") in labels and not replacing:
            problems.append(f"{row.get('id')}: labelled twice")
        replaced += replacing and row.get("id") in labels
        labels[row.get("id")] = row
problems += [f"{i}: no label" for i in ids if i not in labels]
problems += [f"{i}: no such posting" for i in labels if i not in set(ids)]
for problem in problems:
    print(problem)
if problems:
    sys.exit(1)

rows = [labels[i] for i in ids]
with open(sys.argv[2], "w", encoding="utf-8", newline="\n") as out:
    for row in sorted(rows, key=lambda r: r["id"]):
        out.write(json.dumps(row, ensure_ascii=False) + "\n")

required = [len(r.get("required") or []) for r in rows]
nice = [len(r.get("nice_to_have") or []) for r in rows]
print(f"labels: {len(rows)}, replaced by a later pass: {replaced}")
print(f"postings with a stack list: {sum(bool(r.get('stack')) for r in rows)}")
print(f"required entries per posting: median {statistics.median(required)}, min {min(required)}, max {max(required)}, none in {required.count(0)}")
print(f"nice-to-have entries per posting: median {statistics.median(nice)}, min {min(nice)}, max {max(nice)}, none in {nice.count(0)}")
print(f"any-of entries: {sum(len(e['skills']) > 1 for r in rows for f in ('required', 'nice_to_have') for e in r.get(f) or [])}")
print("seniority:", dict(collections.Counter(r["seniority"]["level"] for r in rows).most_common()))
print(f"postings stating years: {sum(r.get('min_years') is not None for r in rows)}")
kinds = collections.Counter((c["kind"], "must" if c["hard"] else "preferred") for r in rows for c in r.get("constraints") or [])
print("constraints:", {f"{k} ({h})": n for (k, h), n in kinds.most_common()})
skills = collections.Counter(s.lower() for r in rows for e in r.get("required") or [] for s in e["skills"])
print("most asked:", ", ".join(f"{s} {n}" for s, n in skills.most_common(25)))
print(f"with a note: {sum(bool(r.get('note')) for r in rows)}")
