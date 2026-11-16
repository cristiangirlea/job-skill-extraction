"""Tests of the repository guard and of the tools' edge cases, on invented data."""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_tools import DESCRIPTION, LABEL, POSTING, TOOLS, read, run, write


def load(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Guard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, files):
        for name, content in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                path.write_bytes(content)
            else:
                path.write_text(content, encoding="utf-8")
        result = subprocess.run([sys.executable, str(TOOLS / "check_repo.py"), str(self.root)], capture_output=True, text=True)
        for name in files:
            (self.root / name).unlink()
        return result

    def test_the_repositorys_own_kinds_of_files_pass(self):
        result = self.check({
            "README.md": "See https://example.com/a/b or write to someone@example.com. Use and/or, a 3/4 share, ~/notes.\n",
            "tools/a.py": "print('ok')\n",
            "tools/prompt-v2.txt": "Return JSON.\n",
            "tests/test_a.py": "pass\n",
            ".claude/skills/check/SKILL.md": "Run the checks.\n",
        })
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("5 files checked, 0 findings", result.stdout)

    def test_data_and_other_kinds_of_files_are_refused(self):
        refused = [
            "data/postings.jsonl", "tests/data/x.jsonl", "tools/runs/a.json", "review.md", "work/p-1.txt",
            "companies.txt", "MANIFEST.json", "aliases.json", "batch-01.ids", "tools/labels.jsonl",
            "adapter_model.safetensors", "tools/deep/a.py", "notes/README.md", "tools/prompt.txt",
        ]
        for name in refused:
            result = self.check({name: "{}\n"})
            self.assertEqual(result.returncode, 1, name)
            self.assertIn("not a kind of file this repository holds", result.stdout, name)

    def test_machine_paths_and_addresses_are_refused(self):
        # The samples are put together here so this file itself passes the check.
        backslash, slash, at, percent = chr(92), "/", "@", "%"
        lines = {
            "an upper-case drive": f"saved to E:{backslash}work{backslash}x",
            "a lower-case drive": "saved to e:" + slash + "work/x",
            "a shell drive path": "cd " + slash + "e/work/x",
            "a mounted drive path": "cd " + slash + "mnt/e/work/x",
            "a network path": f"copy {backslash}{backslash}server{backslash}share",
            "a personal folder": "in " + slash + "home" + slash + "someone/x",
            "an environment folder": "under " + percent + "USERPROFILE" + percent + " here",
            "an address": "write to Jane.Doe" + at + "Gmail.COM",
            "an address on a look-alike domain": "write to x" + at + "example.community",
        }
        for what, line in lines.items():
            result = self.check({"README.md": line + "\n"})
            self.assertEqual(result.returncode, 1, what)
            self.assertIn("README.md:1:", result.stdout, what)

    def test_more_spellings_of_a_machine_path_are_refused(self):
        slash, percent, tick = "/", "%", chr(96)
        lines = {
            "after a backtick": "see " + tick + slash + "e/work/personal" + tick,
            "after a colon": "path:" + slash + "e/work",
            "an upper-case shell drive": "cd " + slash + "E/work/x",
            "an upper-case mounted drive": "cd " + slash + "mnt/E/work/x",
            "a lower-case personal folder": "in " + slash + "users" + slash + "someone/x",
            "a lower-case environment folder": "under " + percent + "userprofile" + percent,
            "an address behind an allowed-looking domain": "x" + "@" + "users.noreply.github.com.elsewhere.ro",
        }
        for what, line in lines.items():
            result = self.check({"README.md": line + "\n"})
            self.assertEqual(result.returncode, 1, what)

    def test_a_file_with_an_accented_name_is_checked(self):
        for name in ("review-ü.md", "tools/zürich.jsonl"):
            result = self.check({name: "{}\n"})
            self.assertEqual(result.returncode, 1, name)
            self.assertIn("not a kind of file this repository holds", result.stdout, name)

    def test_a_staged_file_removed_from_the_folder_is_still_checked(self):
        for name, content in (("staged.md", "x\n"), ("README.md", "saved to e:" + "/" + "work/x\n")):
            path = self.root / name
            path.write_text(content, encoding="utf-8")
            subprocess.run(["git", "add", name], cwd=self.root, check=True)
            path.unlink()
            result = subprocess.run([sys.executable, str(TOOLS / "check_repo.py"), str(self.root)], capture_output=True, text=True, encoding="utf-8")
            subprocess.run(["git", "rm", "-q", "--cached", name], cwd=self.root, check=True)
            self.assertEqual(result.returncode, 1, name + result.stdout)

    def test_a_staged_copy_that_differs_from_the_folder_is_checked(self):
        path = self.root / "README.md"
        path.write_text("saved to e:" + "/" + "work/x\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=self.root, check=True)
        path.write_text("clean\n", encoding="utf-8")
        result = subprocess.run([sys.executable, str(TOOLS / "check_repo.py"), str(self.root)], capture_output=True, text=True, encoding="utf-8")
        subprocess.run(["git", "rm", "-q", "-f", "--cached", "README.md"], cwd=self.root, check=True)
        path.unlink()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("README.md:1: a drive path of one computer", result.stdout)

    def test_large_and_binary_files_are_refused(self):
        self.assertIn("larger than", self.check({"tools/big.py": "#" * 300_001}).stdout)
        self.assertIn("not text", self.check({"tools/blob.py": bytes([255, 254, 0, 200])}).stdout)

    def test_private_names_are_refused_when_listed(self):
        (self.root / ".gitignore").write_text(".private-terms\n", encoding="utf-8")
        (self.root / ".private-terms").write_text("Quillstone\n", encoding="utf-8")
        result = self.check({"README.md": "Built for the quillstone project.\n"})
        self.assertEqual(result.returncode, 1)
        self.assertIn("README.md:1: a private name", result.stdout)


class Scorer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.postings, self.labels, self.run_file = self.dir / "postings.jsonl", self.dir / "labels.jsonl", self.dir / "run.jsonl"
        write(self.postings, [POSTING])
        write(self.labels, [LABEL])

    def tearDown(self):
        self.tmp.cleanup()

    def score(self, answer, *more):
        write(self.run_file, [answer])
        result = run("score.py", "score", self.postings, self.labels, self.run_file, "-", *more)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_names_match_as_documented(self):
        same = load("score").Names({}).same
        self.assertTrue(same("C", "c"))
        self.assertTrue(same("RAG", "RAG pipelines"))
        self.assertTrue(same("LLMs", "LLM"))
        self.assertFalse(same("C", "C level"))
        self.assertFalse(same("Java", "JavaScript"))
        self.assertFalse(same("Go", "Rust"))

    def test_f1_is_zero_not_missing_when_nothing_is_right(self):
        f1 = load("score").f1
        self.assertEqual(f1(0.0, 0.5), 0.0)
        self.assertEqual(f1(0.5, 0.5), 0.5)
        self.assertIsNone(f1(None, 0.5))

    def test_the_second_alternative_finds_an_either_or_entry(self):
        answer = json.loads(json.dumps(LABEL))
        answer["required"][0] = {"skills": ["Rust"], "quote": "Strong Go or Rust"}
        self.assertEqual(self.score(answer)["skills_found"]["recall_of_required"], 1.0)

    def test_precision_counts_what_was_not_asked(self):
        answer = json.loads(json.dumps(LABEL))
        answer["required"] = answer["required"][:2] + [{"skills": ["Salesforce"], "quote": "used by teams"}]
        answer["nice_to_have"] = []
        metrics = self.score(answer)
        # Go, Rust and Kubernetes are asked, Salesforce is not: 3 of 4.
        self.assertEqual(metrics["skills_found"]["precision_any_list"], 0.75)
        self.assertEqual(metrics["skills_found"]["where_predicted_skills_land"]["not asked"], 0.25)
        self.assertEqual(metrics["nice_as_nice"]["f1"], None)

    def test_a_required_skill_filed_as_a_bonus_is_found_but_misfiled(self):
        answer = json.loads(json.dumps(LABEL))
        answer["nice_to_have"].append(answer["required"].pop(1))
        metrics = self.score(answer)
        self.assertEqual(metrics["skills_found"]["recall_of_required"], 1.0)
        self.assertEqual(metrics["required_as_required"]["recall"], 0.75)
        self.assertEqual(metrics["nice_as_nice"]["precision"], 0.5)

    def test_constraints_are_scored_by_kind_and_language(self):
        answer = json.loads(json.dumps(LABEL))
        answer["constraints"] = [
            {"kind": "language", "value": "German (fluent)", "hard": True, "quote": "Fluent English"},
            {"kind": "citizenship", "value": "EU", "hard": True, "quote": "Fluent English"},
            {"kind": "degree", "value": "any", "hard": False, "quote": "Fluent English"},
        ]
        constraints = self.score(answer)["hard_constraints"]
        self.assertEqual((constraints["gold"], constraints["predicted"]), (1, 2))
        self.assertEqual(constraints["recall"], 0.0)
        self.assertEqual(constraints["languages_recall"], 0.0)

    def test_an_unusable_answer_is_wrong_on_every_row(self):
        labels = json.loads(json.dumps(LABEL))
        labels["seniority"], labels["min_years"] = {"level": "unspecified", "quote": None}, None
        write(self.labels, [labels])
        metrics = self.score({"id": "p-1", "error": "not usable JSON"})
        self.assertEqual(metrics["seniority"]["label_right"], 0.0)
        self.assertEqual(metrics["seniority"]["level_number_right"], 0.0)
        self.assertEqual(metrics["min_years"]["right"], 0.0)

    def test_a_keyword_run_is_compared_on_what_it_can_know(self):
        metrics = self.score({"id": "p-1", "mentions": {"go": 2, "kubernetes": 1, "salesforce": 1}, "seniority_level": 3, "warnings": []})
        self.assertEqual(metrics["skills_found"]["recall_of_required"], 0.5)
        self.assertEqual(metrics["skills_found"]["precision_any_list"], round(2 / 3, 3))
        self.assertEqual(metrics["seniority"]["level_number_right"], 1.0)
        self.assertNotIn("required_as_required", metrics)
        # The label's only hard constraint is English, which a keyword run is not asked about.
        self.assertEqual(metrics["hard_constraints"]["gold"], 0)

    def test_a_posting_the_keyword_run_skipped_does_not_turn_it_into_a_model_run(self):
        write(self.postings, [POSTING, {**POSTING, "id": "p-2"}])
        write(self.labels, [LABEL, {**LABEL, "id": "p-2"}])
        metrics = self.score({"id": "p-1", "mentions": {"go": 1}, "seniority_level": 3, "warnings": []})
        self.assertEqual(metrics["postings_without_output"], 1)
        self.assertNotIn("required_as_required", metrics)
        self.assertNotIn("min_years", metrics)

    def test_a_split_limits_the_postings_scored(self):
        write(self.postings, [{**POSTING, "split": "dev"}, {**POSTING, "id": "p-2", "split": "train"}])
        write(self.labels, [LABEL, {**LABEL, "id": "p-2"}])
        self.assertEqual(self.score(LABEL)["postings"], 2)
        metrics = self.score(LABEL, "--split", "dev")
        self.assertEqual((metrics["postings"], metrics["postings_without_output"]), (1, 0))


class OtherTools(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def pool(self, companies):
        text = DESCRIPTION + "\n" + "More about the role and the team. " * 30
        rows = [
            {**POSTING, "id": "from-the-source", "external_id": str(n), "company": company, "title": f"Backend Engineer {n}", "description": f"Posting {n}. " + text}
            for n, company in enumerate(companies, 1)
        ]
        path = self.dir / "pool.jsonl"
        write(path, rows)
        return path, rows

    def test_merging_replaces_and_refuses(self):
        postings, first, second, merged = (self.dir / n for n in ("postings.jsonl", "a.jsonl", "b.jsonl", "merged.jsonl"))
        write(postings, [POSTING])
        write(first, [LABEL])
        write(second, [{**LABEL, "note": "second pass"}])
        self.assertEqual(run("merge_labels.py", postings, merged, first).returncode, 0)
        self.assertEqual(read(merged)[0]["note"], "")
        twice = run("merge_labels.py", postings, merged, first, second)
        self.assertEqual(twice.returncode, 1)
        self.assertIn("p-1: labelled twice", twice.stdout)
        replaced = run("merge_labels.py", postings, merged, first, "--replace", second)
        self.assertEqual(replaced.returncode, 0, replaced.stdout)
        self.assertEqual(read(merged)[0]["note"], "second pass")
        write(second, [{**LABEL, "id": "p-9"}])
        unknown = run("merge_labels.py", postings, merged, first, second)
        self.assertEqual(unknown.returncode, 1)
        self.assertIn("p-9: no such posting", unknown.stdout)

    def test_merging_accepts_a_label_without_optional_lists(self):
        postings, labels = self.dir / "postings.jsonl", self.dir / "labels.jsonl"
        write(postings, [POSTING])
        write(labels, [{"id": "p-1", "required": [], "seniority": {"level": "unspecified", "quote": None}}])
        self.assertEqual(run("verify_labels.py", postings, labels).returncode, 0)
        self.assertEqual(run("merge_labels.py", postings, self.dir / "merged.jsonl", labels).returncode, 0)

    def test_sampled_sets_get_their_own_ids(self):
        pool, _ = self.pool(["Lumenfold GmbH", "Harborline", "Quillstone AG", "Brightmoor Ltd"])
        test_dir = self.dir / "test"
        self.assertEqual(run("sample_testset.py", pool, test_dir).returncode, 0)
        rows = read(test_dir / "postings.jsonl")
        self.assertEqual(sorted(r["id"] for r in rows), ["ts-001", "ts-002", "ts-003", "ts-004"])
        self.assertEqual(len({r["company_key"] for r in rows}), 4)

    def test_training_postings_keep_companies_apart(self):
        companies = ["Lumenfold GmbH", "Lumenfold HQ", "Harborline", "Harborline", "Quillstone AG", "Brightmoor Ltd"]
        pool, rows = self.pool(companies)
        test_dir, train_dir = self.dir / "test", self.dir / "train"
        test_dir.mkdir()
        write(test_dir / "postings.jsonl", [{**rows[0], "id": "ts-001"}])
        (test_dir / "companies.txt").write_text("lumenfold\n", encoding="utf-8")
        result = run("sample_trainset.py", test_dir, train_dir, pool)
        self.assertEqual(result.returncode, 0, result.stderr)
        sampled = read(train_dir / "postings.jsonl")
        # "Lumenfold HQ" is the test company written another way, so it is held out too.
        self.assertEqual(sorted(r["company"] for r in sampled), ["Brightmoor Ltd", "Harborline", "Harborline", "Quillstone AG"])
        self.assertEqual(sorted(r["id"] for r in sampled), ["tr-001", "tr-002", "tr-003", "tr-004"])
        splits = {r["company"]: set() for r in sampled}
        for r in sampled:
            splits[r["company"]].add(r["split"])
        self.assertTrue(all(len(s) == 1 for s in splits.values()), splits)

    def test_examples_drop_the_labellers_fields_and_need_every_label(self):
        postings, labels, prompt, out = (self.dir / n for n in ("postings.jsonl", "labels.jsonl", "prompt.txt", "examples.jsonl"))
        label = json.loads(json.dumps(LABEL))
        label["note"] = "unsure about the level"
        label["required"][0]["en"] = ["Go", "Rust"]
        write(postings, [{**POSTING, "split": "dev"}])
        write(labels, [label])
        prompt.write_text("Return JSON.", encoding="utf-8")
        self.assertEqual(run("build_examples.py", postings, labels, prompt, out).returncode, 0)
        example = read(out)[0]
        self.assertEqual(example["split"], "dev")
        self.assertNotIn("note", example["assistant"])
        self.assertNotIn('"en"', example["assistant"])
        write(postings, [POSTING, {**POSTING, "id": "p-2"}])
        missing = run("build_examples.py", postings, labels, prompt, out)
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn("p-2: no label", missing.stderr)

    def test_batches_leave_out_labelled_postings(self):
        postings, done, work = self.dir / "postings.jsonl", self.dir / "done.jsonl", self.dir / "work"
        write(postings, [POSTING, {**POSTING, "id": "p-2"}, {**POSTING, "id": "p-3"}])
        self.assertEqual(run("split_batches.py", postings, "-", work, 2).returncode, 0)
        ids = sorted((work / "batch-01.ids").read_text().split() + (work / "batch-02.ids").read_text().split())
        self.assertEqual(ids, ["p-1", "p-2", "p-3"])
        write(done, [LABEL])
        work2 = self.dir / "work2"
        self.assertEqual(run("split_batches.py", postings, done, work2, 1).returncode, 0)
        self.assertEqual((work2 / "batch-01.ids").read_text().split(), ["p-2", "p-3"])
        self.assertTrue((work2 / "p-2.txt").read_text(encoding="utf-8").startswith("ID: p-2\nCOMPANY: Lumenfold GmbH\nTITLE: "))

    def test_only_this_computer_counts_as_a_local_server(self):
        loopback = load("run_model").loopback
        self.assertTrue(loopback("http://127.0.0.1:8081/v1/chat/completions"))
        self.assertTrue(loopback("http://localhost:8081/v1/chat/completions"))
        for url in (
            "http://127.0.0.1:1" + "@" + "elsewhere.example/v1",
            "http://127.0.0.1.elsewhere.example:8081/v1",
            "https://127.0.0.1:8081/v1",
            "http://localhost/v1",
            "http://192.168.1.5:8081/v1",
            "file:///tmp/x",
        ):
            self.assertFalse(loopback(url), url)


if __name__ == "__main__":
    unittest.main()
