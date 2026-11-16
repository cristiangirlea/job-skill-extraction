"""Checks labels against their postings and writes a sheet for a person to review.

Usage: python -I verify_labels.py <postings.jsonl> <labels.jsonl> [<review.md>]

Exit code 1 when a label breaks a rule a script can check (LABELS.md).
"""

import json
import sys
from pathlib import Path

LEVELS = {"intern", "junior", "mid", "senior", "lead", "staff", "principal", "manager", "director", "unspecified"}
KINDS = {
    "citizenship", "work_authorization", "clearance", "language", "location", "timezone",
    "travel", "degree", "certification", "contract", "other",
}


def check_quote(quote, text, where, errors):
    if not isinstance(quote, str) or not quote.strip():
        errors.append(f"{where}: empty quote")
        return False
    if "\n" in quote:
        errors.append(f"{where}: quote spans lines")
        return False
    if quote not in text:
        errors.append(f"{where}: quote not in the posting: {quote[:70]!r}")
        return False
    return True


def check(label, posting):
    errors = []
    text = posting["title"] + "\n" + posting["description"]
    for field in ("required", "nice_to_have", "stack"):
        for n, entry in enumerate(label.get(field, [])):
            where = f"{field}[{n}]"
            skills = entry.get("skills") or []
            if not skills:
                errors.append(f"{where}: no skills")
            if check_quote(entry.get("quote"), text, where, errors):
                for skill in skills:
                    if skill.lower() not in entry["quote"].lower():
                        errors.append(f"{where}: skill {skill!r} is not in its quote")
            if "en" in entry and len(entry["en"]) != len(skills):
                errors.append(f"{where}: 'en' must name each skill")
    seniority = label.get("seniority") or {}
    if seniority.get("level") not in LEVELS:
        errors.append(f"seniority: unknown level {seniority.get('level')!r}")
    elif seniority["level"] == "unspecified":
        if seniority.get("quote") is not None:
            errors.append("seniority: unspecified takes no quote")
    else:
        check_quote(seniority.get("quote"), text, "seniority", errors)
    years = label.get("min_years")
    if years is not None:
        if not isinstance(years.get("years"), int) or years["years"] < 0:
            errors.append("min_years: years must be a whole number")
        quoted = check_quote(years.get("quote"), text, "min_years", errors)
        # A number written as a word ("zeven jaar") cannot be checked here.
        if quoted and any(c.isdigit() for c in years["quote"]) and str(years.get("years")) not in years["quote"]:
            errors.append("min_years: the number is not in its quote")
    for n, item in enumerate(label.get("constraints", [])):
        where = f"constraints[{n}]"
        if item.get("kind") not in KINDS:
            errors.append(f"{where}: unknown kind {item.get('kind')!r}")
        if not isinstance(item.get("hard"), bool):
            errors.append(f"{where}: hard must be true or false")
        if not item.get("value"):
            errors.append(f"{where}: no value")
        check_quote(item.get("quote"), text, where, errors)
    return errors


def cell(text):
    return str(text).replace("|", "\\|")


def sheet(label, posting):
    out = [f"## {posting['id']}: {posting['title']}", "", f"{posting['company']}, {posting['location'] or 'no location'}. {posting['url']}", ""]
    out += ["| | Skill | Quote from the posting |", "|---|---|---|"]
    for field, name in (("required", "Required"), ("nice_to_have", "Nice to have"), ("stack", "Team's stack")):
        for entry in label.get(field, []):
            skills = " or ".join(entry["skills"])
            if entry.get("en"):
                skills += " (" + " or ".join(entry["en"]) + ")"
            out.append(f"| {name} | {cell(skills)} | {cell(entry['quote'])} |")
    seniority = label["seniority"]
    out.append(f"| Seniority | {seniority['level']} | {cell(seniority.get('quote') or 'no level word in the posting')} |")
    years = label.get("min_years")
    out.append(f"| Years | {years['years'] if years else 'none stated'} | {cell(years['quote']) if years else ''} |")
    for item in label.get("constraints", []):
        strength = "must" if item["hard"] else "preferred"
        out.append(f"| Constraint ({strength}) | {item['kind']}: {cell(item['value'])} | {cell(item['quote'])} |")
    if label.get("note"):
        out += ["", f"Note: {label['note']}"]
    return out + [""]


def main():
    postings = {}
    for line in open(sys.argv[1], encoding="utf-8"):
        row = json.loads(line)
        postings[row["id"]] = row
    labels = [json.loads(line) for line in open(sys.argv[2], encoding="utf-8") if line.strip()]
    failed = 0
    review = ["# Pilot labels to check", "", "Each row is one label with the sentence it rests on. Mark what is wrong or missing.", ""]
    for label in labels:
        posting = postings.get(label["id"])
        if posting is None:
            print(f"{label['id']}: no such posting")
            failed += 1
            continue
        errors = check(label, posting)
        failed += bool(errors)
        counts = f"{len(label.get('required', []))} required, {len(label.get('nice_to_have', []))} nice to have, {len(label.get('stack', []))} stack, {len(label.get('constraints', []))} constraints"
        print(f"{label['id']}: {'FAIL' if errors else 'ok'} ({counts})")
        for error in errors:
            print("   " + error.encode("ascii", "replace").decode())
        review += sheet(label, posting)
    if len(sys.argv) > 3 and not failed:
        Path(sys.argv[3]).write_text("\n".join(review), encoding="utf-8", newline="\n")
        print(f"review sheet written: {sys.argv[3]}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
