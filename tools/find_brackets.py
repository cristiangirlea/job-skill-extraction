"""Finds labelled lines whose plain bracket holds names that got no entry (LABELS.md, change 18).

Usage: python -I find_brackets.py <out.jsonl> <labels.jsonl> [<labels.jsonl> ...]

Writes one row per posting that has such a line: its id, the label file it came from, and the
lines to look at (list, quote, the bracket's unlabelled items).
"""

import json
import re
import sys

BRACKET = re.compile(r"\(([^()]{2,160})\)")
EXAMPLE_START = re.compile(r"^\s*(e\.?\s?g\.?|z\.?\s?b\.?|i\.?\s?e\.?|such as|like|for example|for instance|including|incl\.?|bspw\.?|u\.?\s?a\.?|wie|par exemple|bijv\.?|zoals)\b", re.I)
EXAMPLE_END = re.compile(r"(etc\.?|usw\.?|or similar|o\.?\s?ä\.?|and more|\.\.\.|…|u\.?\s?a\.?|among others)\s*$", re.I)
SPLIT = re.compile(r"\s*(?:,|;|/|\band/or\b|\bund/oder\b|\band\b|\bor\b|\bund\b|\boder\b|\bet\b|\bou\b|\ben\b|\bof\b|&|\+(?=\s))\s*", re.I)
NOT_A_NAME = re.compile(r"^(m|w|d|f|x|h|div|all genders|gn|remote|hybrid|onsite|on-site|full[- ]time|part[- ]time|\d[\d\s%+.,-]*|[a-z]{1,2}\d?|s|es|n|in|innen)$", re.I)


def norm(text):
    return re.sub(r"[^\w+#.]+", " ", text.lower()).strip()


def main():
    out_path = sys.argv[1]
    found = 0
    with open(out_path, "w", encoding="utf-8", newline="\n") as out:
        for path in sys.argv[2:]:
            for line in open(path, encoding="utf-8"):
                if not line.strip():
                    continue
                row = json.loads(line)
                labelled = [norm(s) for f in ("required", "nice_to_have", "stack") for e in row.get(f) or [] for s in (e.get("skills") or []) + (e.get("en") or [])]
                lines, seen = [], set()
                for field in ("required", "nice_to_have", "stack"):
                    for entry in row.get(field) or []:
                        quote = entry["quote"]
                        for inner in BRACKET.findall(quote):
                            if EXAMPLE_START.search(inner) or EXAMPLE_END.search(inner):
                                continue
                            items = [i.strip(" .:'\"") for i in SPLIT.split(inner)]
                            items = [i for i in items if i and not NOT_A_NAME.match(i) and len(i.split()) <= 4 and len(i) <= 40]
                            missing = [i for i in items if not any(norm(i) == s or norm(i) in s.split() or s in norm(i) for s in labelled if s)]
                            key = (quote, inner)
                            if missing and key not in seen:
                                seen.add(key)
                                lines.append({"list": field, "quote": quote, "unlabelled": missing})
                if lines:
                    found += 1
                    out.write(json.dumps({"id": row["id"], "file": path, "lines": lines}, ensure_ascii=False) + "\n")
    print(f"{found} postings have a plain bracket with unlabelled names")


if __name__ == "__main__":
    main()
