"""Prints the full text of chosen postings, for labelling.

Usage: python -I show_posting.py <postings.jsonl> <id> [<id> ...]
"""

import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
wanted = set(sys.argv[2:])
for line in open(sys.argv[1], encoding="utf-8"):
    row = json.loads(line)
    if row["id"] in wanted:
        print(f"===== {row['id']} | {row['company']} | {row['location']} | {row['language']}")
        print(f"TITLE: {row['title']}")
        print(row["description"])
        print()
