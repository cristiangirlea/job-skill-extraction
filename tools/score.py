"""Scores a run (a model's labels, or a keyword matcher's output) against a set's labels.

Usage:
  python -I score.py strings <labels.jsonl> <run.jsonl> <strings.txt>
      writes every skill string of both files, one per line, to build an alias map from
  python -I score.py score <postings.jsonl> <labels.jsonl> <run.jsonl> <aliases.json|-> [<metrics.json>] [--split NAME]

--split scores only the postings whose "split" field is NAME ("dev" of a training set). A
posting without a usable answer counts as wrong on every row.

A run file holds label-shaped rows as LABELS.md describes them, or rows of a keyword matcher:
{"id", "mentions": {term: count}, "seniority_level": number or null, "warnings": [text]}.

The alias map is optional ("-" for none): a JSON object from a skill string to the canonical
terms it names, for example {"Golang": ["go"], "K8s": ["kubernetes"]}.

How two skill names are compared: they match when the alias map gives them a term in common
("Golang" and "Go"), when their words are equal after lowercasing and dropping a plural s, or
when the words of one stand together inside the other ("RAG" in "RAG pipelines"). An entry with
several skills is found when any one of them is.
"""

import json
import re
import sys
from collections import Counter

LEVELS = {"intern": 0, "junior": 1, "mid": 2, "senior": 3, "lead": 4, "staff": 4, "manager": 4, "principal": 5, "director": 5}
STOP = {"and", "or", "of", "the", "in", "for", "with", "a", "an", "to", "und", "oder", "von", "mit", "im"}
LANGUAGES = {
    "english": "english", "englisch": "english", "englischkenntnisse": "english", "engels": "english", "anglais": "english",
    "german": "german", "deutsch": "german", "deutschkenntnisse": "german", "duits": "german",
    "french": "french", "französisch": "french", "frans": "french", "français": "french",
    "dutch": "dutch", "nederlands": "dutch", "niederländisch": "dutch",
    "spanish": "spanish", "italian": "italian", "portuguese": "portuguese", "polish": "polish",
    "swedish": "swedish", "danish": "danish", "norwegian": "norwegian", "finnish": "finnish",
    "japanese": "japanese", "mandarin": "mandarin", "chinese": "mandarin", "arabic": "arabic",
    "hebrew": "hebrew", "turkish": "turkish", "czech": "czech", "romanian": "romanian",
}
ELIGIBILITY = {"citizenship", "work_authorization", "clearance"}


def tokens(text):
    out = []
    for token in re.sub(r"[^\w+#.]+", " ", text.lower()).split():
        token = token.strip("._")
        if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
            token = token[:-1]
        if token and token not in STOP:
            out.append(token)
    return out


def inside(short, long):
    n = len(short)
    return n > 0 and any(long[i:i + n] == short for i in range(len(long) - n + 1))


class Names:
    def __init__(self, canon):
        self.canon = canon
        self.cache = {}

    def key(self, name):
        if name not in self.cache:
            self.cache[name] = (frozenset(self.canon.get(name.strip(), [])), tuple(tokens(name)))
        return self.cache[name]

    def same(self, a, b):
        (terms_a, words_a), (terms_b, words_b) = self.key(a), self.key(b)
        if terms_a & terms_b:
            return True
        if not words_a or not words_b:
            return False
        if words_a == words_b:
            return True
        short, long = sorted((list(words_a), list(words_b)), key=len)
        # One letter inside a longer name ("C" in "C level") says nothing.
        return sum(map(len, short)) >= 2 and inside(short, long)


def entry_forms(entry):
    return list(entry.get("skills") or []) + list(entry.get("en") or [])


def skills_of(entries):
    return [s for e in entries or [] for s in (e.get("skills") or []) if isinstance(s, str) and s.strip()]


def language_of(value):
    for word in re.findall(r"[^\W\d_]+", str(value).lower()):
        if word in LANGUAGES:
            return LANGUAGES[word]
    return "?"


def constraint_keys(constraints):
    keys = set()
    for c in constraints or []:
        if not isinstance(c, dict) or c.get("hard") is not True:
            continue
        kind = c.get("kind")
        keys.add(f"language:{language_of(c.get('value', ''))}" if kind == "language" else str(kind))
    return keys


def from_rules(row):
    """Reads a keyword matcher's row as a prediction."""
    keys = set()
    for warning in row.get("warnings") or []:
        if warning.startswith("Posting requires eligibility") or warning.startswith("Posting states work authorization"):
            keys.add("eligibility")
        match = re.match(r"Posting requires (\w+) beyond", warning)
        if match:
            keys.add(f"language:{language_of(match.group(1))}")
    return {
        "mentioned": sorted(row.get("mentions") or {}),
        "level_number": row.get("seniority_level"),
        "constraint_keys": keys,
        "rules": True,
    }


def from_labels(row):
    level = ((row.get("seniority") or {}).get("level") or "unspecified").lower()
    years = row.get("min_years")
    if isinstance(years, dict):
        years = years.get("years")
    return {
        "required": skills_of(row.get("required")),
        "nice": skills_of(row.get("nice_to_have")),
        "stack": skills_of(row.get("stack")),
        "level": level,
        "level_number": LEVELS.get(level),
        "years": years if isinstance(years, int) else None,
        "constraint_keys": constraint_keys(row.get("constraints")),
        "rules": False,
    }


def ratio(a, b):
    return round(a / b, 3) if b else None


def f1(p, r):
    if p is None or r is None:
        return None
    return round(2 * p * r / (p + r), 3) if p + r else 0.0


def quotes_check(row, posting):
    text = posting["title"] + "\n" + posting["description"]
    total = good = skills = skills_inside = 0
    items = []
    for field in ("required", "nice_to_have", "stack"):
        items += [(e.get("quote"), e.get("skills") or []) for e in row.get(field) or [] if isinstance(e, dict)]
    items += [(c.get("quote"), []) for c in row.get("constraints") or [] if isinstance(c, dict)]
    for quote, names in items:
        total += 1
        ok = isinstance(quote, str) and quote.strip() and "\n" not in quote and quote in text
        good += bool(ok)
        for name in names:
            skills += 1
            skills_inside += bool(ok and isinstance(name, str) and name.lower() in quote.lower())
    return total, good, skills, skills_inside


def main():
    mode = sys.argv[1]
    if mode == "strings":
        names = set()
        for path in sys.argv[2:4]:
            for line in open(path, encoding="utf-8"):
                if not line.strip():
                    continue
                row = json.loads(line)
                names.update(row.get("mentions") or {})
                for field in ("required", "nice_to_have", "stack"):
                    for entry in row.get(field) or []:
                        if isinstance(entry, dict):
                            names.update(s.strip() for s in entry_forms(entry) if isinstance(s, str) and s.strip())
        with open(sys.argv[4], "w", encoding="utf-8", newline="\n") as out:
            out.write("\n".join(sorted(n.replace("\n", " ") for n in names)) + "\n")
        print(f"{len(names)} skill strings")
        return

    args = sys.argv[2:]
    split = None
    if "--split" in args:
        at = args.index("--split")
        split = args[at + 1]
        del args[at:at + 2]
    postings = {json.loads(l)["id"]: json.loads(l) for l in open(args[0], encoding="utf-8") if l.strip()}
    gold_rows = {json.loads(l)["id"]: json.loads(l) for l in open(args[1], encoding="utf-8") if l.strip()}
    if split:
        gold_rows = {i: r for i, r in gold_rows.items() if postings[i].get("split") == split}
    run_rows = {}
    for line in open(args[2], encoding="utf-8"):
        if line.strip():
            row = json.loads(line)
            run_rows[row.get("id")] = row
    names = Names({} if args[3] == "-" else json.load(open(args[3], encoding="utf-8")))
    metrics_path = args[4] if len(args) > 4 else None
    # One kind per run file: a posting the keyword matcher skipped is still a keyword row.
    keyword_run = any("mentions" in row for row in run_rows.values())

    n = Counter()
    lands = Counter()
    by_language = {}
    for pid, gold_row in gold_rows.items():
        gold = {f: gold_row.get(f) or [] for f in ("required", "nice_to_have", "stack")}
        row = run_rows.get(pid)
        n["postings"] += 1
        # A posting without a usable answer is wrong on every row, never right by default.
        answered = not (row is None or row.get("error"))
        if not answered:
            n["no_output"] += 1
            row = {}
        rules = keyword_run
        pred = from_rules(row) if rules else from_labels(row)
        mentioned = pred["mentioned"] if rules else pred["required"] + pred["nice"] + pred["stack"]

        def hits(entries, predicted):
            return sum(any(names.same(form, p) for form in entry_forms(e) for p in predicted) for e in entries)

        def in_list(name, entries):
            return any(names.same(form, name) for e in entries for form in entry_forms(e))

        lang = by_language.setdefault(postings[pid].get("language", "?"), Counter())
        found_required = hits(gold["required"], mentioned)
        n["gold_required"] += len(gold["required"])
        n["gold_required_found"] += found_required
        lang["gold_required"] += len(gold["required"])
        lang["gold_required_found"] += found_required
        everything = gold["required"] + gold["nice_to_have"] + gold["stack"]
        n["gold_any"] += len(everything)
        n["gold_any_found"] += hits(everything, mentioned)
        for name in mentioned:
            n["predicted"] += 1
            where = next((f for f in ("required", "nice_to_have", "stack") if in_list(name, gold[f])), "not asked")
            lands[where] += 1
        if not rules:
            n["label_rows"] += 1
            n["pred_required"] += len(pred["required"])
            n["pred_required_right"] += sum(in_list(p, gold["required"]) for p in pred["required"])
            n["gold_required_as_required"] += hits(gold["required"], pred["required"])
            n["pred_nice"] += len(pred["nice"])
            n["pred_nice_right"] += sum(in_list(p, gold["nice_to_have"]) for p in pred["nice"])
            n["gold_nice"] += len(gold["nice_to_have"])
            n["gold_nice_as_nice"] += hits(gold["nice_to_have"], pred["nice"])
            total, good, skills, skills_inside = quotes_check(row, postings[pid])
            n["quotes"] += total
            n["quotes_exact"] += good
            n["skills_quoted"] += skills
            n["skills_in_quote"] += skills_inside

        gold_level = (gold_row["seniority"]["level"] or "unspecified").lower()
        gold_number = LEVELS.get(gold_level)
        n["level_number_right"] += answered and pred["level_number"] == gold_number
        if gold_number is None:
            n["gold_no_level"] += 1
            n["gold_no_level_right"] += answered and pred["level_number"] is None
        else:
            n["gold_level"] += 1
            n["gold_level_right"] += answered and pred["level_number"] == gold_number
        if not rules:
            n["level_label_right"] += answered and pred["level"] == gold_level
            gold_years = (gold_row.get("min_years") or {}).get("years")
            n["years_right"] += answered and pred["years"] == gold_years
            if gold_years is not None:
                n["gold_years"] += 1
                n["gold_years_right"] += answered and pred["years"] == gold_years

        gold_keys = constraint_keys(gold_row.get("constraints"))
        pred_keys = pred["constraint_keys"]
        if rules:
            # The rules know eligibility and languages only; compare on those.
            # Their language gate speaks relative to a profile; the run used one that lists English.
            gold_keys = {"eligibility" if k in ELIGIBILITY else k for k in gold_keys if k in ELIGIBILITY or k.startswith("language:") and k != "language:english"}
        n["gold_constraints"] += len(gold_keys)
        n["pred_constraints"] += len(pred_keys)
        n["constraints_right"] += len(gold_keys & pred_keys)
        gold_eligible = bool({"eligibility"} & gold_keys or ELIGIBILITY & gold_keys)
        pred_eligible = bool({"eligibility"} & pred_keys or ELIGIBILITY & pred_keys)
        n["gold_eligibility"] += gold_eligible
        n["pred_eligibility"] += pred_eligible
        n["eligibility_right"] += gold_eligible and pred_eligible
        gold_languages = {k for k in gold_keys if k.startswith("language:")}
        pred_languages = {k for k in pred_keys if k.startswith("language:")}
        n["gold_languages"] += len(gold_languages)
        n["pred_languages"] += len(pred_languages)
        n["languages_right"] += len(gold_languages & pred_languages)

    precision = ratio(n["predicted"] - lands["not asked"], n["predicted"])
    recall = ratio(n["gold_required_found"], n["gold_required"])
    m = {
        "postings": n["postings"],
        "postings_without_output": n["no_output"],
        "skills_found": {
            "predicted_skills": n["predicted"],
            "per_posting": round(n["predicted"] / n["postings"], 1) if n["postings"] else None,
            "precision_any_list": precision,
            "recall_of_required": recall,
            "f1": f1(precision, recall),
            "recall_of_all_entries": ratio(n["gold_any_found"], n["gold_any"]),
            "where_predicted_skills_land": {k: ratio(lands[k], n["predicted"]) for k in ("required", "nice_to_have", "stack", "not asked")},
            "recall_of_required_by_language": {k: ratio(v["gold_required_found"], v["gold_required"]) for k, v in sorted(by_language.items())},
        },
        "seniority": {
            "level_number_right": ratio(n["level_number_right"], n["postings"]),
            "right_when_posting_names_a_level": ratio(n["gold_level_right"], n["gold_level"]),
            "right_when_posting_names_none": ratio(n["gold_no_level_right"], n["gold_no_level"]),
        },
        "hard_constraints": {
            "precision": ratio(n["constraints_right"], n["pred_constraints"]),
            "recall": ratio(n["constraints_right"], n["gold_constraints"]),
            "eligibility_recall": ratio(n["eligibility_right"], n["gold_eligibility"]),
            "eligibility_precision": ratio(n["eligibility_right"], n["pred_eligibility"]),
            "languages_recall": ratio(n["languages_right"], n["gold_languages"]),
            "languages_precision": ratio(n["languages_right"], n["pred_languages"]),
            "gold": n["gold_constraints"], "predicted": n["pred_constraints"],
            "gold_eligibility_postings": n["gold_eligibility"], "gold_languages": n["gold_languages"],
        },
    }
    if n["label_rows"]:
        rp, rr = ratio(n["pred_required_right"], n["pred_required"]), ratio(n["gold_required_as_required"], n["gold_required"])
        np_, nr = ratio(n["pred_nice_right"], n["pred_nice"]), ratio(n["gold_nice_as_nice"], n["gold_nice"])
        m["required_as_required"] = {"precision": rp, "recall": rr, "f1": f1(rp, rr)}
        m["nice_as_nice"] = {"precision": np_, "recall": nr, "f1": f1(np_, nr)}
        m["seniority"]["label_right"] = ratio(n["level_label_right"], n["postings"])
        m["min_years"] = {"right": ratio(n["years_right"], n["postings"]), "right_when_stated": ratio(n["gold_years_right"], n["gold_years"])}
        m["quotes"] = {"exact": ratio(n["quotes_exact"], n["quotes"]), "skill_inside_its_quote": ratio(n["skills_in_quote"], n["skills_quoted"])}
    print(json.dumps(m, indent=2))
    if metrics_path:
        with open(metrics_path, "w", encoding="utf-8", newline="\n") as out:
            out.write(json.dumps(m, indent=2) + "\n")


if __name__ == "__main__":
    main()
