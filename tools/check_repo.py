"""Fails when anything but the repository's own kinds of files is about to be committed.

Usage: python tools/check_repo.py [<repository-root>]

Looks at every file git tracks or would add. Posting text belongs to the employers and labels,
review sheets, work files and company lists all carry it, so the check fails closed: a file is
accepted only when its path is one of the kinds listed in ALLOWED. Accepted files are then read
for machine paths and e-mail addresses, in the folder and as staged.

Private names that must never appear (a user name, a private project) can be listed, one per
line, in a file named .private-terms at the root. It is ignored by git, so the names themselves
are not published; the check reads it when it is there.
"""

import fnmatch
import re
import subprocess
import sys
from pathlib import Path

ALLOWED = [
    "LICENSE", ".gitignore", ".gitattributes",
    "README.md", "RESULTS.md", "MODEL_CARD.md", "LABELS.md", "AGENTS.md", "CLAUDE.md",
    "tools/*.py", "tools/prompt-*.txt", "tools/labeller-brief.md",
    "tests/*.py",
    ".github/workflows/*.yml",
    ".claude/settings.json", ".claude/skills/*/SKILL.md", ".claude/rules/*.md",
]
MAX_BYTES = 300_000
TEXT_RULES = [
    ("a drive path of one computer", re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/](?!/)")),
    ("a drive path of one computer", re.compile(r"(?<![\w.~/-])/(?:mnt/)?[a-z]/\w", re.I)),
    ("a network path of one computer", re.compile(r"""(?:^|[\s"'(=`:])\\\\\w""")),
    ("a personal folder", re.compile(r"[\\/](?:Users|home)[\\/][A-Za-z]|/roo[t]/|%[A-Z]{4,}%", re.I)),
    ("an e-mail address", re.compile(r"[\w.+-]+@(?!(?:users\.noreply\.github\.com|example\.(?:com|org))(?![\w-]|\.\w))[\w-]+(?:\.[\w-]+)*\.[a-z]{2,}", re.I)),
]


def allowed(name):
    # fnmatch lets "*" cross "/", so the number of path parts must match as well.
    return any(fnmatch.fnmatchcase(name, pattern) and name.count("/") == pattern.count("/") for pattern in ALLOWED)


def git_names(root, *options):
    # -z and quotePath=false: a name with an accent comes as it is, not quoted and escaped.
    out = subprocess.run(["git", "-c", "core.quotePath=false", "ls-files", "-z", *options], cwd=root, capture_output=True, check=True).stdout
    return [name for name in out.decode("utf-8", "surrogateescape").split("\0") if name]


def read_findings(name, content, private):
    if len(content) > MAX_BYTES:
        return [f"{name}: larger than {MAX_BYTES // 1000} KB"]
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return [f"{name}: not text"]
    findings = []
    for number, line in enumerate(text.splitlines(), 1):
        for what, pattern in TEXT_RULES:
            if pattern.search(line):
                findings.append(f"{name}:{number}: {what}")
        lowered = line.lower()
        if any(term in lowered for term in private):
            findings.append(f"{name}:{number}: a private name")
    return findings


def check(root):
    listed = git_names(root, "--cached", "--others", "--exclude-standard")
    staged = set(git_names(root, "--cached"))
    private = []
    terms = root / ".private-terms"
    if terms.is_file():
        private = [t.strip().lower() for t in terms.read_text(encoding="utf-8").splitlines() if t.strip()]
    findings = []
    for name in listed:
        shown = name.encode("utf-8", "backslashreplace").decode("utf-8")
        if not allowed(name):
            findings.append(f"{shown}: not a kind of file this repository holds (see ALLOWED in tools/check_repo.py)")
            continue
        # The folder's copy and the staged copy can differ, and the commit takes the staged one.
        versions = []
        path = root / name
        if path.is_file():
            versions.append(path.read_bytes())
        if name in staged:
            shown_staged = subprocess.run(["git", "show", f":{name}"], cwd=root, capture_output=True)
            if shown_staged.returncode != 0:
                findings.append(f"{shown}: the staged copy could not be read")
            elif shown_staged.stdout not in versions:
                versions.append(shown_staged.stdout)
        for content in versions:
            for finding in read_findings(shown, content, private):
                if finding not in findings:
                    findings.append(finding)
    return listed, findings


def main():
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
    listed, findings = check(root)
    for finding in findings:
        print(finding)
    print(f"{len(listed)} files checked, {len(findings)} findings")
    sys.exit(1 if findings else 0)


if __name__ == "__main__":
    main()
