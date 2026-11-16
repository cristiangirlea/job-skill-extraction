"""Prints the make-up of a test set without its posting text.

Usage: python -I show_sample.py <postings.jsonl> [rows]
"""

import collections
import json
import random
import sys

rows = [json.loads(line) for line in open(sys.argv[1], encoding="utf-8")]
shown = int(sys.argv[2]) if len(sys.argv) > 2 else 40
per_company = collections.Counter(r["company_key"] for r in rows)
print("companies by number of postings:", dict(collections.Counter(per_company.values())))
print("by provider:", dict(collections.Counter(r["provider"] for r in rows)))
random.seed(1)
for r in random.sample(rows, min(shown, len(rows))):
    line = f"{r['id']} {r['provider'][:5]} {r['language']} {len(r['description']):>5} | {r['company'][:28]} | {r['title'][:70]}"
    print(line.encode("ascii", "replace").decode())
