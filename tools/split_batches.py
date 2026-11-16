"""Splits the unlabelled postings into batches of about equal reading length.

Usage: python -I split_batches.py <postings.jsonl> <done-labels.jsonl|-> <work-dir> <batches>

Postings that already have a label in <done-labels.jsonl> are left out ("-" for none).
Writes one text file per posting (work-dir/<id>.txt) and one id list per batch
(work-dir/batch-NN.ids).
"""

import json
import sys
from pathlib import Path

postings = [json.loads(line) for line in open(sys.argv[1], encoding="utf-8")]
done = set() if sys.argv[2] == "-" else {json.loads(line)["id"] for line in open(sys.argv[2], encoding="utf-8") if line.strip()}
work = Path(sys.argv[3])
count = int(sys.argv[4])
work.mkdir(parents=True, exist_ok=True)

todo = sorted((p for p in postings if p["id"] not in done), key=lambda p: -len(p["description"]))
batches = [[] for _ in range(count)]
sizes = [0] * count
for posting in todo:
    n = sizes.index(min(sizes))
    batches[n].append(posting["id"])
    sizes[n] += len(posting["description"])
    text = f"ID: {posting['id']}\nCOMPANY: {posting['company']}\nTITLE: {posting['title']}\n\n{posting['description']}\n"
    (work / f"{posting['id']}.txt").write_text(text, encoding="utf-8", newline="\n")
for n, ids in enumerate(batches, 1):
    (work / f"batch-{n:02d}.ids").write_text("\n".join(sorted(ids)) + "\n", encoding="utf-8", newline="\n")
    print(f"batch-{n:02d}: {len(ids)} postings, {sizes[n - 1]} characters")
