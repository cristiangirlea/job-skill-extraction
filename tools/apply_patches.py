"""Adds the entries of a patch file to labels.

Usage: python -I apply_patches.py <labels-in.jsonl> <patch.jsonl> <labels-out.jsonl>

A patch row is {"id": ..., "add": [{"list": "required", "skills": [...], "quote": "..."}]}.
An entry is skipped when all its skills are already labelled in that posting.
"""

import json
import sys

patches = {}
for line in open(sys.argv[2], encoding="utf-8"):
    if line.strip():
        row = json.loads(line)
        patches.setdefault(row["id"], []).extend(row["add"])

added = skipped = touched = 0
with open(sys.argv[3], "w", encoding="utf-8", newline="\n") as out:
    for line in open(sys.argv[1], encoding="utf-8"):
        if not line.strip():
            continue
        row = json.loads(line)
        extra = patches.pop(row["id"], [])
        before = added
        have = {s.lower() for f in ("required", "nice_to_have", "stack") for e in row.get(f) or [] for s in e.get("skills") or []}
        for entry in extra:
            if entry["list"] not in ("required", "nice_to_have", "stack") or all(s.lower() in have for s in entry["skills"]):
                skipped += 1
                continue
            row.setdefault(entry["list"], []).append({"skills": entry["skills"], "quote": entry["quote"]})
            have.update(s.lower() for s in entry["skills"])
            added += 1
        touched += added > before
        out.write(json.dumps(row, ensure_ascii=False) + "\n")
print(f"added {added} entries to {touched} postings, skipped {skipped}, patches for unknown ids: {len(patches)}")
