"""Draws training and development postings, none from a company of the test set.

Usage: python -I sample_trainset.py <test-dir> <out-dir> <pool.jsonl> [<pool.jsonl> ...]

Uses the test set's filters (sample_testset.py). Writes postings.jsonl (each row with
"split": "train" or "dev", split by company), companies.txt and MANIFEST.json.
"""

import hashlib
import importlib.util
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

spec = importlib.util.spec_from_file_location("testset", Path(__file__).with_name("sample_testset.py"))
ts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ts)

SEED = 20261112
TARGET = 600
DEV = 100
BOARD_SHARE = 240
PER_BOARD_COMPANY = 6
PER_COMPANY = 2
MAX_CHARS = 16000


def body_hash(text):
    return hashlib.sha256(text[:1500].encode("utf-8")).hexdigest()


def main():
    test_dir, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    test_companies = set((test_dir / "companies.txt").read_text(encoding="utf-8").split("\n")) - {""}
    test_rows = [json.loads(l) for l in (test_dir / "postings.jsonl").read_text(encoding="utf-8").splitlines()]
    test_ids = {(r["provider"], r["external_id"]) for r in test_rows}
    test_bodies = {body_hash(r["description"]) for r in test_rows}

    def held_out(company):
        if company in test_companies:
            return True
        # "lumenfold" and "lumenfoldhq" are one company written two ways.
        return any(len(a) >= 5 and len(b) >= 5 and (a.startswith(b) or b.startswith(a)) for a in (company,) for b in test_companies)

    dropped = Counter()
    seen_ids, seen_roles, seen_bodies = set(test_ids), set(), set(test_bodies)
    kept = []
    pool_rows = 0
    for path in sys.argv[3:]:
        for line in open(path, encoding="utf-8"):
            if not line.strip():
                continue
            row = json.loads(line)
            pool_rows += 1
            ident = (row["provider"], row["external_id"])
            if ident in seen_ids:
                dropped["fetched twice, or in the test set"] += 1
                continue
            seen_ids.add(ident)
            company = ts.company_key(row["company"])
            if not company:
                dropped["no company name"] += 1
                continue
            if held_out(company):
                dropped["company is in the test set"] += 1
                continue
            size = len(row["description"])
            if size < ts.MIN_CHARS or size > MAX_CHARS:
                dropped["description too short or too long"] += 1
                continue
            board = row["provider"] in ts.BOARDS
            if board and (not ts.BOARD_TITLE.search(row["title"]) or ts.NOT_FOR_BOARDS.search(row["title"])):
                dropped["board title outside the search terms"] += 1
                continue
            if not board and not ts.TECH_TITLE.search(row["title"]):
                dropped["aggregator title not a technical role"] += 1
                continue
            role, body = (company, ts.title_key(row["title"])), body_hash(row["description"])
            if role in seen_roles or body in seen_bodies:
                dropped["same role posted again"] += 1
                continue
            seen_roles.add(role)
            seen_bodies.add(body)
            row["company_key"] = company
            kept.append(row)

    rng = random.Random(SEED)
    by_company = defaultdict(list)
    for row in kept:
        by_company[row["company_key"]].append(row)
    boards, others = [], []
    for company in sorted(by_company):
        rows = by_company[company]
        rng.shuffle(rows)
        # A company seen on a board and on an aggregator counts as a board company.
        if any(r["provider"] in ts.BOARDS for r in rows):
            boards.append([r for r in rows if r["provider"] in ts.BOARDS][:PER_BOARD_COMPANY])
        else:
            others.append(rows[:PER_COMPANY])
    rng.shuffle(boards)
    rng.shuffle(others)

    def take(groups, target):
        out = []
        for group in groups:
            if len(out) >= target:
                break
            out.append(group)
        return out

    chosen_boards = take(boards, 10 ** 9)
    board_rows = [r for g in chosen_boards for r in g]
    rng.shuffle(board_rows)
    board_rows = board_rows[:BOARD_SHARE]
    other_groups, count = [], 0
    for group in others:
        if count >= TARGET - len(board_rows):
            break
        other_groups.append(group)
        count += len(group)
    sample = board_rows + [r for g in other_groups for r in g]
    sample = sample[:TARGET]

    # Development companies: whole companies, chosen at random, until about DEV postings.
    companies = sorted({r["company_key"] for r in sample})
    rng.shuffle(companies)
    per_company = Counter(r["company_key"] for r in sample)
    dev_companies, dev_count = set(), 0
    for company in companies:
        if dev_count >= DEV:
            break
        dev_companies.add(company)
        dev_count += per_company[company]

    rng.shuffle(sample)
    lines = []
    for n, row in enumerate(sample, 1):
        # The set's own id and split come last: a pool row may carry fields of the same name.
        row = {**row, "id": f"tr-{n:03d}", "split": "dev" if row["company_key"] in dev_companies else "train", "language": ts.language(row["description"])}
        sample[n - 1] = row
        lines.append(json.dumps(row, ensure_ascii=False))
    body = "\n".join(lines) + "\n"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "postings.jsonl").write_text(body, encoding="utf-8", newline="\n")
    (out_dir / "companies.txt").write_text("\n".join(sorted(companies)) + "\n", encoding="utf-8", newline="\n")
    chars = sorted(len(r["description"]) for r in sample)
    manifest = {
        "what": "Training and development postings for job-posting skill extraction. Posting text belongs to the employers: never commit it.",
        "seed": SEED,
        "pool_rows": pool_rows,
        "pool_after_filters": len(kept),
        "dropped": dict(dropped),
        "postings": len(sample),
        "by_split": dict(Counter(r["split"] for r in sample)),
        "companies": len(companies),
        "dev_companies": len(dev_companies),
        "companies_shared_with_the_test_set": len(set(companies) & test_companies),
        "by_provider": dict(Counter(r["provider"] for r in sample)),
        "by_language_guess": dict(Counter(r["language"] for r in sample)),
        "description_chars": {"min": chars[0], "median": chars[len(chars) // 2], "max": chars[-1]},
        "rules": {"per_board_company": PER_BOARD_COMPANY, "per_company_on_aggregators": PER_COMPANY, "max_description_chars": MAX_CHARS},
        "postings_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
    }
    (out_dir / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
