"""Tests for scan_secrets.py, review_threads.py and doctor.py. Run: python3 -m unittest discover tests"""
import json
import os
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def git(*args, cwd):
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args], cwd=cwd, check=True,
                   capture_output=True)


class ScanSecretsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        git("init", "-q", "-b", "main", cwd=self.repo)
        (self.repo / "old.py").write_text('password = "hunter2hunter2"\n')  # pre-existing: must be ignored
        git("add", "-A", cwd=self.repo)
        git("commit", "-qm", "base", cwd=self.repo)
        git("switch", "-qc", "feature", cwd=self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def scan(self):
        return subprocess.run([sys.executable, str(SCRIPTS / "scan_secrets.py"), str(self.repo), "main"],
                              capture_output=True, text=True)

    def commit(self, files):
        for name, content in files.items():
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        git("add", "-A", cwd=self.repo)
        git("commit", "-qm", "change", cwd=self.repo)

    def test_clean_branch(self):
        self.commit({"app.py": 'API_URL = "https://example.com"\npassword = os.environ["DB_PASSWORD"]\n',
                     ".env.example": "DB_PASSWORD=changeme\n"})
        r = self.scan()
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_detects_and_masks(self):
        self.commit({
            "config.py": 'db_password = "S3cr3t-Pr0d-Value"\nAWS = "AKIAABCDEFGHIJKLMNOP"\n',
            "deploy/key.pem": "-----BEGIN RSA PRIVATE KEY-----\nabc\n",
            ".env": "TOKEN=ghp_" + "a" * 36 + "\n",
            "notes.md": "db: postgres://admin:realpass123@db.internal/app\n",
        })
        r = self.scan()
        self.assertEqual(r.returncode, 1)
        for expected in ("config.py:1: hard-coded secret", "config.py:2: AWS access key", "deploy/key.pem",
                         ".env: sensitive file", "credentials in URL"):
            self.assertIn(expected, r.stdout)
        self.assertNotIn("S3cr3t-Pr0d-Value", r.stdout)
        self.assertNotIn("old.py", r.stdout)

    def test_placeholders_and_allow_marker(self):
        self.commit({"t.py": 'password = "your-password-here"\n'
                             'token = "ghp_' + "b" * 36 + '"  # ai-workspace:allow-secret\n'})
        self.assertEqual(self.scan().returncode, 0)


class FakeCliCase(unittest.TestCase):
    """Puts fake `gh` and `glab` executables first on PATH; they answer from canned JSON files."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bin = Path(self.tmp.name)
        self.log = self.bin / "calls.log"
        fake = textwrap.dedent(f"""\
            #!{sys.executable}
            import json, os, sys
            args = sys.argv[1:]
            stdin = "" if sys.stdin.isatty() else sys.stdin.read()
            with open({str(self.log)!r}, "a") as f:
                f.write(json.dumps({{"prog": os.path.basename(sys.argv[0]), "args": args, "stdin": stdin}}) + "\\n")
            joined = " ".join(args)
            responses = json.load(open({str(self.bin / 'responses.json')!r}))
            for needle, body in responses.items():
                if needle in joined:
                    print(json.dumps(body)); sys.exit(0)
            print("no canned response for: " + joined, file=sys.stderr); sys.exit(1)
            """)
        for prog in ("gh", "glab"):
            path = self.bin / prog
            path.write_text(fake)
            path.chmod(path.stat().st_mode | stat.S_IEXEC)
        self.env = {**os.environ, "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}"}

    def tearDown(self):
        self.tmp.cleanup()

    def responses(self, mapping):
        (self.bin / "responses.json").write_text(json.dumps(mapping))

    def run_rt(self, *args, stdin=None):
        return subprocess.run([sys.executable, str(SCRIPTS / "review_threads.py"), *args], input=stdin,
                              capture_output=True, text=True, env=self.env)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]


@unittest.skipIf(os.name == "nt", "fake CLIs use a shebang")
class ReviewThreadsTest(FakeCliCase):
    def test_github_lists_only_unresolved(self):
        self.responses({"reviewThreads": {"data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": [
            {"id": "T1", "isResolved": False, "isOutdated": False, "path": "api/x.py", "line": 4,
             "comments": {"nodes": [{"author": {"login": "rev"}, "body": "Handle None", "url": "u1"}]}},
            {"id": "T2", "isResolved": True, "path": "a", "line": 1, "comments": {"nodes": []}},
        ]}}}}}})
        r = self.run_rt("list", "https://github.com/o/r/pull/7")
        self.assertEqual(r.returncode, 0, r.stderr)
        threads = json.loads(r.stdout)
        self.assertEqual([t["id"] for t in threads], ["T1"])
        self.assertEqual(threads[0]["body"], "Handle None")

    def test_github_reply_passes_body_on_stdin(self):
        self.responses({"addPullRequestReviewThreadReply": {"data": {"addPullRequestReviewThreadReply":
                                                                    {"comment": {"url": "https://x/c/1"}}}}})
        r = self.run_rt("reply", "https://github.com/o/r/pull/7", "T1", stdin="Fixed in abc123; thanks!")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("https://x/c/1", r.stdout)
        call = self.calls()[-1]
        self.assertIn("body=@-", call["args"])
        self.assertEqual(call["stdin"], "Fixed in abc123; thanks!")

    def test_gitlab_list_and_checks(self):
        self.responses({
            "/discussions": [
                {"id": "D1", "notes": [{"resolvable": True, "resolved": False, "body": "Rename this",
                                        "author": {"username": "rev"}, "position": {"new_path": "a.go", "new_line": 9}}]},
                {"id": "D2", "notes": [{"resolvable": True, "resolved": True, "body": "ok", "author": {}}]},
                {"id": "D3", "notes": [{"system": True, "body": "added 1 commit"}]},
            ],
            "/pipelines/55/jobs": [{"id": 1, "name": "test", "status": "failed", "web_url": "j1"},
                                   {"id": 2, "name": "lint", "status": "failed", "allow_failure": True},
                                   {"id": 3, "name": "build", "status": "success"}],
            "merge_requests/3": {"sha": "abc", "head_pipeline": {"id": 55}},
        })
        url = "https://gitlab.example.com/grp/sub/app/-/merge_requests/3"
        r = self.run_rt("list", url)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([(t["id"], t["path"], t["line"]) for t in json.loads(r.stdout)], [("D1", "a.go", 9)])
        self.assertIn("grp%2Fsub%2Fapp", " ".join(self.calls()[-1]["args"]))
        r = self.run_rt("checks", url)
        self.assertEqual(r.returncode, 0, r.stderr)
        summary = json.loads(r.stdout)
        self.assertEqual(summary["state"], "failed")
        self.assertEqual([c["name"] for c in summary["failed"]], ["test"])

    def test_bad_url(self):
        r = self.run_rt("list", "https://example.com/nope")
        self.assertEqual(r.returncode, 1)
        self.assertIn("not a GitHub PR or GitLab MR URL", r.stderr)


class DoctorTest(unittest.TestCase):
    def test_reports_missing_workspace_and_codebase(self):
        with tempfile.TemporaryDirectory() as d:
            r = subprocess.run([sys.executable, str(SCRIPTS / "doctor.py"), "--root", d], capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)
            self.assertIn("workspace.yaml", r.stdout)
            Path(d, "workspace.yaml").write_text("version: 1\n")
            r = subprocess.run([sys.executable, str(SCRIPTS / "doctor.py"), "--root", d, "--codebases", "api",
                                "--tracker", "trello"], capture_output=True, text=True,
                               env={**os.environ, "TRELLO_API_KEY": "", "TRELLO_TOKEN": "x"})
            self.assertRegex(r.stdout, r"FAIL\s+codebase api\s+not cloned")
            self.assertRegex(r.stdout, r"WARN\s+env TRELLO_API_KEY\s+not set")
            self.assertRegex(r.stdout, r"OK\s+env TRELLO_TOKEN\s+set\n")  # value never printed


if __name__ == "__main__":
    unittest.main()
