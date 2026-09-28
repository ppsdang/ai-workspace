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
