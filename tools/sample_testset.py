"""Draws the frozen test set from a pool of fetched postings (one JSON object per line, see README.md).

Usage: python -I sample_testset.py <pool.jsonl> <out-dir> [--commit SHA]

Writes postings.jsonl (the sample), companies.txt (companies that training
data must never contain) and MANIFEST.json (how the sample was drawn).
"""

import hashlib
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

SEED = 20261111
TARGET = 200
PER_BOARD = 25  # each employer on a board
# Providers whose rows are one employer's own career board. Every other provider value is
# read as an aggregator that lists many employers.
BOARDS = {"greenhouse", "lever", "ashby", "smartrecruiters"}
PER_COMPANY = 2  # each company on an aggregator
MIN_CHARS = 600

TECH_TITLE = re.compile(
    r"engineer|developer|entwickler|programmer|software|architect|devops|sre\b|"
    r"data scien|machine learning|\bml\b|\bai\b|\bki\b|backend|frontend|full.?stack|"
    r"administrator|sysadmin|platform|cloud|security|informatiker|\bit\b",
    re.I,
)
NOT_FOR_BOARDS = re.compile(r"\bintern(ship)?\b|\bstudent\b", re.I)
BOARD_TITLE = re.compile(r"engineer|developer|architect", re.I)
COMPANY_SUFFIX = re.compile(
    r"\b(gmbh|mbh|ag|se|kg|ug|inc|llc|ltd|limited|corp|corporation|co|company|group|holding|bv|sa|srl|plc)\b"
)
GERMAN = re.compile(r"\b(und|der|die|das|wir|mit|für|sie|bei|eine[rnm]?|deine?|unser[e]?)\b", re.I)


def company_key(name: str) -> str:
    key = re.sub(r"[^a-z0-9 ]", " ", name.lower())
    key = COMPANY_SUFFIX.sub(" ", key)
    return " ".join(key.split())


def title_key(title: str) -> str:
    key = re.sub(r"\([^)]*\)", " ", title.lower())
    key = re.split(r"\s[-|,@]\s|\s-\s", key)[0]
    key = re.sub(r"\b(remote|emea|amer|apac|usa?|uk|canada|germany|spain|india)\b", " ", key)
    return " ".join(re.sub(r"[^a-z0-9+#. ]", " ", key).split())


def language(text: str) -> str:
    words = max(1, len(text.split()))
    return "de" if len(GERMAN.findall(text)) / words > 0.06 else "en"


def main() -> None:
    pool_path, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    commit = sys.argv[sys.argv.index("--commit") + 1] if "--commit" in sys.argv else ""
    rows = [json.loads(line) for line in pool_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    dropped = Counter()
    seen_ids, seen_roles, seen_bodies = set(), set(), set()
    kept = []
    for row in rows:
        ident = (row["provider"], row["external_id"])
        if ident in seen_ids:
            dropped["same posting fetched twice"] += 1
            continue
        seen_ids.add(ident)
        if len(row["description"]) < MIN_CHARS:
            dropped["description too short"] += 1
            continue
        board = row["provider"] in BOARDS
        if board and (not BOARD_TITLE.search(row["title"]) or NOT_FOR_BOARDS.search(row["title"])):
            dropped["board title outside the source's search terms"] += 1
            continue
        if not board and not TECH_TITLE.search(row["title"]):
            dropped["aggregator title not a technical role"] += 1
            continue
        company = company_key(row["company"])
        if not company:
            dropped["no company name"] += 1
            continue
        role = (company, title_key(row["title"]))
        body = hashlib.sha256(row["description"][:1500].encode("utf-8")).hexdigest()
        if role in seen_roles or body in seen_bodies:
            dropped["same role posted again (another location)"] += 1
            continue
        seen_roles.add(role)
        seen_bodies.add(body)
        row["company_key"] = company
        kept.append(row)

    rng = random.Random(SEED)
    by_board = defaultdict(list)
    by_company = defaultdict(list)
    for row in kept:
        if row["provider"] in BOARDS:
            by_board[row["company_key"]].append(row)
        else:
            by_company[(row["provider"], row["company_key"])].append(row)

    sample = []
    for board in sorted(by_board):
        picks = by_board[board]
        rng.shuffle(picks)
        sample += picks[:PER_BOARD]
    board_companies = set(by_board)

    aggregator = defaultdict(list)
    taken_companies = set(board_companies)
    for (provider, company) in sorted(by_company):
        if company in taken_companies:
            dropped["company already in the sample from another source"] += len(by_company[(provider, company)])
            continue
        taken_companies.add(company)
        picks = by_company[(provider, company)]
        rng.shuffle(picks)
        aggregator[provider] += picks[:PER_COMPANY]

    # The smallest aggregators go in whole, the largest fills what is left.
    smallest_first = sorted(aggregator, key=lambda p: (len(aggregator[p]), p))
    for position, provider in enumerate(smallest_first):
        picks = aggregator[provider]
        rng.shuffle(picks)
        room = len(picks) if position < len(smallest_first) - 1 else max(0, TARGET - len(sample))
        sample += picks[:room]
        dropped["beyond the target size"] += len(picks) - len(picks[:room])
    dropped["beyond the target size"] += max(0, len(sample) - TARGET)
    sample = sample[:TARGET]

    rng.shuffle(sample)
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = []
    for n, row in enumerate(sample, 1):
        # The set's own id comes last: a pool row may carry an "id" of its own.
        row = {**row, "id": f"ts-{n:03d}", "language": language(row["description"])}
        sample[n - 1] = row
        lines.append(json.dumps(row, ensure_ascii=False))
    body = "\n".join(lines) + "\n"
    (out_dir / "postings.jsonl").write_text(body, encoding="utf-8", newline="\n")
    companies = sorted({row["company_key"] for row in sample})
    (out_dir / "companies.txt").write_text("\n".join(companies) + "\n", encoding="utf-8", newline="\n")
    chars = sorted(len(row["description"]) for row in sample)
    manifest = {
        "what": "Frozen test set for job-posting skill extraction. Posting text belongs to the employers: never commit it.",
        "seed": SEED,
        "source_commit": commit,
        "pool_rows": len(rows),
        "pool_after_filters": len(kept),
        "dropped": dict(dropped),
        "postings": len(sample),
        "companies": len(companies),
        "by_provider": dict(Counter(row["provider"] for row in sample)),
        "by_language_guess": dict(Counter(row["language"] for row in sample)),
        "description_chars": {"min": chars[0], "median": chars[len(chars) // 2], "max": chars[-1]},
        "rules": {
            "per_board": PER_BOARD,
            "per_company_on_aggregators": PER_COMPANY,
            "min_description_chars": MIN_CHARS,
            "held_out": "every company in companies.txt is excluded from training data",
        },
        "postings_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
    }
    (out_dir / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
