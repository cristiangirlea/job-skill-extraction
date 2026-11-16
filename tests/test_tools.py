"""Tests of the tools, on invented postings. Run: python -m unittest discover -s tests -v"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"

DESCRIPTION = "\n".join([
    "Lumenfold builds billing software used by teams at Northwind and Contoso.",
    "",
    "What you will do",
    "• Build services in Go on Kubernetes",
    "",
    "Requirements",
    "• 5+ years of backend experience",
    "• Strong Go or Rust",
    "• Message queues (Kafka, NATS)",
    "• Monitoring tools (e.g. Prometheus)",
    "• Fluent English",
    "",
    "Nice to have",
    "• Terraform experience is a plus",
])
POSTING = {"id": "p-1", "provider": "board", "external_id": "1", "company": "Lumenfold GmbH", "title": "Senior Backend Engineer", "location": "Berlin", "description": DESCRIPTION, "url": "https://example.com/1"}
LABEL = {
    "id": "p-1",
    "required": [
        {"skills": ["Go", "Rust"], "quote": "Strong Go or Rust"},
        {"skills": ["Kubernetes"], "quote": "Build services in Go on Kubernetes"},
        {"skills": ["Message queues"], "quote": "Message queues (Kafka, NATS)"},
        {"skills": ["Monitoring"], "quote": "Monitoring tools (e.g. Prometheus)"},
    ],
    "nice_to_have": [{"skills": ["Terraform"], "quote": "Terraform experience is a plus"}],
    "seniority": {"level": "senior", "quote": "Senior Backend Engineer"},
    "min_years": {"years": 5, "quote": "5+ years of backend experience"},
    "constraints": [{"kind": "language", "value": "English (fluent)", "hard": True, "quote": "Fluent English"}],
    "note": "",
}


def write(path, rows):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def read(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def run(tool, *args):
    return subprocess.run([sys.executable, "-I", str(TOOLS / tool), *map(str, args)], capture_output=True, text=True, encoding="utf-8")


class Tools(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.postings, self.labels = self.dir / "postings.jsonl", self.dir / "labels.jsonl"
        write(self.postings, [POSTING])
        write(self.labels, [LABEL])

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_grounded_label_passes_the_checker(self):
        result = run("verify_labels.py", self.postings, self.labels)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("p-1: ok", result.stdout)

    def test_an_invented_quote_or_skill_fails_the_checker(self):
        for change in ("quote", "skill", "level"):
            bad = json.loads(json.dumps(LABEL))
            if change == "quote":
                bad["nice_to_have"][0]["quote"] = "Terraform is required"
            elif change == "skill":
                bad["required"][1]["skills"] = ["Nomad"]
            else:
                bad["seniority"]["level"] = "wizard"
            write(self.labels, [bad])
            result = run("verify_labels.py", self.postings, self.labels)
            self.assertEqual(result.returncode, 1, change)
            self.assertIn("p-1: FAIL", result.stdout)

    def test_labels_score_perfectly_against_themselves(self):
        result = run("score.py", "score", self.postings, self.labels, self.labels, "-")
        self.assertEqual(result.returncode, 0, result.stderr)
        metrics = json.loads(result.stdout)
        self.assertEqual(metrics["skills_found"]["recall_of_required"], 1.0)
        self.assertEqual(metrics["skills_found"]["precision_any_list"], 1.0)
        self.assertEqual(metrics["required_as_required"]["f1"], 1.0)
        self.assertEqual(metrics["seniority"]["label_right"], 1.0)
        self.assertEqual(metrics["hard_constraints"]["recall"], 1.0)

    def test_a_worse_answer_scores_lower(self):
        answer = json.loads(json.dumps(LABEL))
        answer["required"] = answer["required"][:2] + [{"skills": ["Salesforce"], "quote": "used by teams"}]
        answer["nice_to_have"], answer["seniority"] = [], {"level": "staff", "quote": None}
        run_file = self.dir / "run.jsonl"
        write(run_file, [answer])
        metrics = json.loads(run("score.py", "score", self.postings, self.labels, run_file, "-").stdout)
        self.assertEqual(metrics["skills_found"]["recall_of_required"], 0.5)
        self.assertLess(metrics["skills_found"]["precision_any_list"], 1.0)
        self.assertEqual(metrics["seniority"]["label_right"], 0.0)
        self.assertLess(metrics["quotes"]["skill_inside_its_quote"], 1.0)

    def test_an_either_or_entry_is_found_by_one_of_its_skills(self):
        answer = json.loads(json.dumps(LABEL))
        answer["required"][0] = {"skills": ["Golang"], "quote": "Strong Go or Rust"}
        run_file, aliases = self.dir / "run.jsonl", self.dir / "aliases.json"
        write(run_file, [answer])
        aliases.write_text(json.dumps({"Golang": ["go"], "Go": ["go"]}), encoding="utf-8")
        metrics = json.loads(run("score.py", "score", self.postings, self.labels, run_file, aliases).stdout)
        self.assertEqual(metrics["skills_found"]["recall_of_required"], 1.0)

    def test_a_missing_answer_counts_as_empty(self):
        run_file = self.dir / "run.jsonl"
        write(run_file, [{"id": "p-1", "error": "not usable JSON"}])
        metrics = json.loads(run("score.py", "score", self.postings, self.labels, run_file, "-").stdout)
        self.assertEqual(metrics["postings_without_output"], 1)
        self.assertEqual(metrics["skills_found"]["recall_of_required"], 0.0)

    def test_the_bracket_finder_sees_plain_brackets_only(self):
        out = self.dir / "brackets.jsonl"
        result = run("find_brackets.py", out, self.labels)
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = read(out)
        self.assertEqual([r["id"] for r in rows], ["p-1"])
        self.assertEqual([line["unlabelled"] for line in rows[0]["lines"]], [["Kafka", "NATS"]])

    def test_a_patch_adds_entries_once(self):
        patch, out = self.dir / "patch.jsonl", self.dir / "patched.jsonl"
        add = [
            {"list": "required", "skills": ["Kafka", "NATS"], "quote": "Message queues (Kafka, NATS)"},
            {"list": "required", "skills": ["Kubernetes"], "quote": "Build services in Go on Kubernetes"},
        ]
        write(patch, [{"id": "p-1", "add": add}])
        result = run("apply_patches.py", self.labels, patch, out)
        self.assertIn("added 1 entries to 1 postings, skipped 1", result.stdout)
        self.assertEqual(len(read(out)[0]["required"]), 5)
        self.assertEqual(run("verify_labels.py", self.postings, out).returncode, 0)

    def test_merging_refuses_a_posting_without_a_label(self):
        write(self.postings, [POSTING, {**POSTING, "id": "p-2"}])
        result = run("merge_labels.py", self.postings, self.dir / "merged.jsonl", self.labels)
        self.assertEqual(result.returncode, 1)
        self.assertIn("p-2: no label", result.stdout)

    def test_examples_hold_the_answer_the_model_is_asked_for(self):
        prompt, out = self.dir / "prompt.txt", self.dir / "examples.jsonl"
        prompt.write_text("Return JSON.", encoding="utf-8")
        self.assertEqual(run("build_examples.py", self.postings, self.labels, prompt, out).returncode, 0)
        example = read(out)[0]
        answer = json.loads(example["assistant"])
        self.assertEqual(list(answer), ["required", "nice_to_have", "stack", "seniority", "min_years", "constraints"])
        self.assertEqual(answer["min_years"], 5)
        self.assertTrue(example["user"].startswith("TITLE: Senior Backend Engineer\n"))
        self.assertNotIn("note", answer)

    def test_training_postings_never_come_from_a_test_company(self):
        long_text = DESCRIPTION + "\n" + "More about the role and the team. " * 30
        pool = [
            {**POSTING, "external_id": str(n), "company": company, "title": f"Backend Engineer {n}", "description": f"Posting {n}. " + long_text}
            for n, company in enumerate(["Lumenfold GmbH", "Lumenfold Inc", "Harborline", "Quillstone AG", "Brightmoor Ltd"], 1)
        ]
        pool_file, test_dir, train_dir = self.dir / "pool.jsonl", self.dir / "test", self.dir / "train"
        write(pool_file, pool)
        test_dir.mkdir()
        write(test_dir / "postings.jsonl", [{**pool[0], "id": "ts-001"}])
        (test_dir / "companies.txt").write_text("lumenfold\n", encoding="utf-8")
        result = run("sample_trainset.py", test_dir, train_dir, pool_file)
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = read(train_dir / "postings.jsonl")
        self.assertEqual(sorted(r["company"] for r in rows), ["Brightmoor Ltd", "Harborline", "Quillstone AG"])
        self.assertTrue(all(r["split"] in ("train", "dev") for r in rows))
        manifest = json.loads((train_dir / "MANIFEST.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["companies_shared_with_the_test_set"], 0)

    def test_the_repository_holds_no_data_or_machine_paths(self):
        result = subprocess.run([sys.executable, str(TOOLS / "check_repo.py")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout)


if __name__ == "__main__":
    unittest.main()
