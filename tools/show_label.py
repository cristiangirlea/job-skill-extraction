"""Prints the labels of chosen postings, one JSON object per line.

Usage: python -I show_label.py <labels.jsonl> <id> [<id> ...]
"""

import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
wanted = set(sys.argv[2:])
for line in open(sys.argv[1], encoding="utf-8"):
    if line.strip() and json.loads(line)["id"] in wanted:
        print(line.strip())
