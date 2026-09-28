"""Tests for scripts/ci.py (Jenkins against a local mock server, custom commands)."""
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CI = ROOT / "scripts" / "ci.py"


class MockJenkins(BaseHTTPRequestHandler):
    routes = {}
    calls = []

    def _reply(self, method):
        MockJenkins.calls.append((method, self.path, self.headers.get("Authorization")))
        body = MockJenkins.routes.get((method, self.path.split("?")[0]))
        if body is None:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(201 if method == "POST" else 200)
        self.end_headers()
        self.wfile.write(body.encode() if isinstance(body, str) else json.dumps(body).encode())

    def do_GET(self):
        self._reply("GET")

    def do_POST(self):
        self._reply("POST")

    def log_message(self, *a):
        pass


def build(number, sha, result=None, building=False, job_url="http://j/job/payroll/job/backend"):
    return {"number": number, "url": f"{job_url}/{number}/", "result": result,
            "building": building, "actions": [{}, {"lastBuiltRevision": {"SHA1": sha}}]}


class JenkinsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), MockJenkins)
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        MockJenkins.routes, MockJenkins.calls = {}, []
        self.env = {**os.environ, "JENKINS_USER": "dev", "JENKINS_TOKEN": "tok"}

    def ci(self, *args):
        r = subprocess.run([sys.executable, str(CI), "--provider", "jenkins", "--url", self.base, *args],
                           capture_output=True, text=True, env=self.env)
        return r

    def test_multibranch_failed_build_with_stages(self):
        branch_job = "/job/payroll/job/backend/job/feature%252FT-1-x"
        b = build(7, "abc123def", result="FAILURE", job_url=self.base + branch_job)
        MockJenkins.routes[("GET", branch_job + "/api/json")] = {"builds": [b]}
        MockJenkins.routes[("GET", branch_job + "/7/wfapi/describe")] = {
            "stages": [{"name": "Build", "status": "SUCCESS"}, {"name": "Unit tests", "status": "FAILED"}]}
        r = self.ci("status", "--job", "payroll/backend", "--branch", "feature/T-1-x", "--sha", "abc123")
        self.assertEqual(r.returncode, 0, r.stderr)
        s = json.loads(r.stdout)
        self.assertEqual(s["state"], "failed")
        self.assertEqual(s["failed"][0]["failed_stages"], ["Unit tests"])
        self.assertTrue(MockJenkins.calls[0][2].startswith("Basic "))

    def test_single_job_matched_by_commit_and_pending(self):
        MockJenkins.routes[("GET", "/job/payroll/job/backend/api/json")] = {
            "builds": [build(12, "fff000", building=True), build(11, "abc999", result="SUCCESS")]}
        r = self.ci("status", "--job", "payroll/backend", "--branch", "main", "--sha", "fff000")
        self.assertEqual(json.loads(r.stdout)["state"], "pending", r.stderr)
        r = self.ci("status", "--job", "payroll/backend", "--branch", "main", "--sha", "abc999")
        self.assertEqual(json.loads(r.stdout)["state"], "passed")
        r = self.ci("status", "--job", "payroll/backend", "--branch", "main", "--sha", "0000000")
        out = json.loads(r.stdout)
        self.assertEqual(out["state"], "none")
        self.assertIn("no Jenkins build found", out["note"])

    def test_log_tail_and_foreign_url_rejected(self):
        MockJenkins.routes[("GET", "/job/x/5/consoleText")] = "\n".join(f"line {i}" for i in range(500))
        r = self.ci("log", "--build", f"{self.base}/job/x/5/", "--tail", "3")
        self.assertEqual(r.stdout.split(), ["line", "497", "line", "498", "line", "499"])
        r = self.ci("log", "--build", "https://evil.example.com/job/x/5/")
        self.assertEqual(r.returncode, 1)

    def test_rerun_posts_build(self):
        MockJenkins.routes[("GET", "/job/payroll/job/backend/api/json")] = {"builds": []}
        MockJenkins.routes[("POST", "/job/payroll/job/backend/build")] = ""
        r = self.ci("rerun", "--job", "payroll/backend", "--branch", "main")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(("POST", "/job/payroll/job/backend/build"), [(m, p) for m, p, _ in MockJenkins.calls])

    def test_missing_credentials(self):
        self.env = {**os.environ, "JENKINS_USER": "", "JENKINS_TOKEN": ""}
        r = self.ci("status", "--job", "a", "--branch", "main")
        self.assertEqual(r.returncode, 1)
        self.assertIn("JENKINS_USER", r.stderr)


BACKEND = "git@gitlab.example.com:payroll/backend.git"
FRONTEND = "git@gitlab.example.com:payroll/frontend.git"


def shared_build(number, revs, result=None, building=False):
    """A build of a job that checks out several repositories: revs = [(clone_url, sha), ...]."""
    return {"number": number, "url": f"http://j/job/payroll/job/integration/{number}/", "result": result,
            "building": building,
            "actions": [{"lastBuiltRevision": {"SHA1": sha}, "remoteUrls": [url]} for url, sha in revs]}


class SharedJobTest(JenkinsTest):
    JOB = "/job/payroll/job/integration/api/json"

    def status(self, *expect):
        args = ["status", "--job", "payroll/integration", "--branch", "feature/T-5"]
        for url, sha in expect:
            args += ["--expect", f"{url}={sha}"]
        r = self.ci(*args)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_build_must_contain_every_commit(self):
        MockJenkins.routes[("GET", self.JOB)] = {"builds": [
            shared_build(20, [(BACKEND, "bbb222"), (FRONTEND, "fff111")], result="SUCCESS"),
            shared_build(19, [(BACKEND, "bbb111"), (FRONTEND, "fff111")], result="SUCCESS")]}
        out = self.status((BACKEND, "bbb222"), (FRONTEND, "fff222"))
        self.assertEqual(out["state"], "none")
        self.assertIn("has only backend@bbb222", out["note"])

        MockJenkins.routes[("GET", self.JOB)]["builds"].insert(
            0, shared_build(21, [(BACKEND, "bbb222"), (FRONTEND, "fff222")], result="FAILURE"))
        out = self.status((BACKEND, "bbb222"), (FRONTEND, "fff222"))
        self.assertEqual(out["state"], "failed")
        self.assertEqual(out["failed"][0]["name"], "payroll/integration #21")
        self.assertEqual(len(out["commits"]), 2)

    def test_only_changed_repositories_are_expected(self):
        MockJenkins.routes[("GET", self.JOB)] = {"builds": [
            shared_build(8, [(BACKEND, "bbb222"), (FRONTEND, "fff000")], result="SUCCESS")]}
        self.assertEqual(self.status((BACKEND, "bbb222"))["state"], "passed")

    def test_running_build_without_recorded_commits_is_pending(self):
        MockJenkins.routes[("GET", self.JOB)] = {"builds": [shared_build(9, [], building=True)]}
        out = self.status((BACKEND, "bbb222"))
        self.assertEqual(out["state"], "pending")
        self.assertIn("not recorded yet", out["note"])

    def test_commit_is_matched_to_the_right_repository(self):
        # same commit id recorded for another repository must not count
        MockJenkins.routes[("GET", self.JOB)] = {"builds": [
            shared_build(3, [(FRONTEND, "abc123")], result="SUCCESS")]}
        self.assertEqual(self.status((BACKEND, "abc123"))["state"], "none")
        # URL forms differ but name the same repository
        MockJenkins.routes[("GET", self.JOB)] = {"builds": [
            shared_build(4, [("https://gitlab.example.com/payroll/backend", "abc123")], result="SUCCESS")]}
        self.assertEqual(self.status((BACKEND, "abc123"))["state"], "passed")

    def test_rerun_with_branch_parameters(self):
        MockJenkins.routes[("GET", self.JOB)] = {"builds": []}
        MockJenkins.routes[("POST", "/job/payroll/job/integration/buildWithParameters")] = ""
        r = self.ci("rerun", "--job", "payroll/integration", "--branch", "feature/T-5",
                    "--param", "BACKEND_BRANCH={branch:backend}", "--param", "FRONTEND_BRANCH={branch:frontend}",
                    "--param", "LABEL=ai-{branch}", "--affected", "backend",
                    "--base", "backend=main", "--base", "frontend=develop")
        self.assertEqual(r.returncode, 0, r.stderr)
        post = [p for m, p, _ in MockJenkins.calls if m == "POST"][0]
        self.assertIn("BACKEND_BRANCH=feature%2FT-5", post)
        self.assertIn("FRONTEND_BRANCH=develop", post)
        self.assertIn("LABEL=ai-feature%2FT-5", post)

    def test_rerun_rejects_unknown_codebase_or_placeholder(self):
        MockJenkins.routes[("GET", self.JOB)] = {"builds": []}
        r = self.ci("rerun", "--job", "payroll/integration", "--branch", "x", "--param", "A={branch:mobile}")
        self.assertEqual(r.returncode, 1)
        self.assertIn("unknown codebase 'mobile'", r.stderr)
        r = self.ci("rerun", "--job", "payroll/integration", "--branch", "x", "--param", "A={sha}")
        self.assertIn("unknown placeholder", r.stderr)


class JobPatternTest(unittest.TestCase):
    def job(self, *args):
        return subprocess.run([sys.executable, str(CI), "job", *args], capture_output=True, text=True)

    def test_patterns_from_clone_urls(self):
        cases = [
            (["--clone-url", "git@gitlab.oodleslab.com:payroll/backend.git", "--codebase", "backend",
              "--pattern", "{group}/{repo}"], "payroll/backend"),
            (["--clone-url", "https://gitlab.example.com/acme/tools/cli.git", "--codebase", "cli",
              "--pattern", "{owner}/{repo}-ci"], "acme/cli-ci"),
            (["--clone-url", "ssh://git@host:2222/grp/app.git", "--codebase", "app",
              "--pattern", "builds/{codebase}"], "builds/app"),
            (["--clone-url", "git@gitlab.example.com:acme/platform.git", "--codebase", "platform",
              "--component", "api", "--component-pattern", "{repo}/{component}"], "platform/api"),
        ]
        for args, expected in cases:
            with self.subTest(args=args):
                r = self.job(*args)
                self.assertEqual((r.returncode, r.stdout.strip()), (0, expected), r.stderr)

    def test_precedence_and_fallbacks(self):
        base = ["--clone-url", "git@h:payroll/backend.git", "--codebase", "backend", "--pattern", "{group}/{repo}"]
        self.assertEqual(self.job(*base, "--ci-job", "legacy/backend-build").stdout.strip(), "legacy/backend-build")
        # a component without a component pattern falls back to the codebase pattern
        self.assertEqual(self.job(*base, "--component", "api").stdout.strip(), "payroll/backend")
        r = self.job("--clone-url", "git@h:a/b.git", "--codebase", "b")
        self.assertEqual(r.returncode, 3)
        r = self.job("--clone-url", "git@h:a/b.git", "--codebase", "b", "--pattern", "{grup}/{repo}")
        self.assertEqual(r.returncode, 1)
        self.assertIn("unknown placeholder", r.stderr)
        r = self.job("--clone-url", "git@h:a/b.git", "--codebase", "b", "--pattern", "{repo}/{component}")
        self.assertEqual(r.returncode, 1)
        # ci_job: none = only built by shared jobs, even when a pattern exists
        r = self.job(*base, "--ci-job", "none")
        self.assertEqual(r.returncode, 4)


class CustomCITest(unittest.TestCase):
    def test_word_and_json_status_log_rerun(self):
        with tempfile.TemporaryDirectory() as d:
            script = Path(d) / "myci.py"
            script.write_text(textwrap.dedent("""\
                import json, sys
                op = sys.argv[1]
                if op == "status":
                    print("failed" if sys.argv[3] == "bad" else json.dumps({"state": "passed", "checks": []}))
                elif op == "log":
                    print("\\n".join(["a", "b", "c", sys.argv[2]]))
                else:
                    print("retriggered " + sys.argv[2])
                """))
            base = [sys.executable, str(CI), "--provider", "custom",
                    "--status-cmd", f"{sys.executable} {script} status {{codebase}} {{branch}}",
                    "--log-cmd", f"{sys.executable} {script} log {{build}}",
                    "--rerun-cmd", f"{sys.executable} {script} rerun {{branch}}"]
            run = lambda *a: subprocess.run([*base, *a], capture_output=True, text=True)
            self.assertEqual(json.loads(run("status", "--codebase", "api", "--branch", "bad").stdout)["state"], "failed")
            self.assertEqual(json.loads(run("status", "--codebase", "api", "--branch", "ok").stdout)["state"], "passed")
            self.assertEqual(run("log", "--build", "b42", "--tail", "2").stdout.split(), ["c", "b42"])
            self.assertIn("retriggered x", run("rerun", "--branch", "x").stdout)


if __name__ == "__main__":
    unittest.main()
