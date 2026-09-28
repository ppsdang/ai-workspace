"""Tests for scripts/tracker.py. Run: python3 -m unittest discover tests"""
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
TRACKER = ROOT / "scripts" / "tracker.py"


def run(*args, stdin=None, env=None, cwd=None):
    full_env = {**os.environ, **(env or {})}
    return subprocess.run([sys.executable, str(TRACKER), *args], input=stdin, capture_output=True,
                          text=True, env=full_env, cwd=cwd)


class MockApi(BaseHTTPRequestHandler):
    routes = {}
    calls = []

    def _handle(self, method):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode() if length else ""
        MockApi.calls.append((method, self.path, body, self.headers.get("Authorization")))
        path = self.path.split("?")[0]
        payload = MockApi.routes.get((method, path))
        if isinstance(payload, list) and payload and isinstance(payload[0], tuple):
            status, payload = payload.pop(0)
            if status != 200:
                self.send_response(status)
                self.send_header("Retry-After", "0")
                self.end_headers()
                return
        if isinstance(payload, bytes):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(payload)
            return
        if payload is None:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'{"error":"not found"}')
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_PUT(self):
        self._handle("PUT")

    def log_message(self, *a):
        pass


class HttpCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), MockApi)
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        MockApi.routes = {}
        MockApi.calls = []


class JiraTest(HttpCase):
    env = {"JIRA_API_TOKEN": "tok", "JIRA_EMAIL": "dev@example.com"}

    def test_fetch_normalises_issue(self):
        MockApi.routes[("GET", "/rest/api/2/issue/SHOP-1")] = {
            "key": "SHOP-1",
            "fields": {
                "summary": "Add 2FA",
                "description": "Users need OTP.\n\nh3. Acceptance criteria\n* OTP sent by SMS\n* Code expires in 5 min",
                "status": {"name": "To Do"}, "issuetype": {"name": "Story"}, "priority": {"name": "High"},
                "labels": ["auth"],
                "comment": {"comments": [{"author": {"displayName": "PM"}, "created": "2026-09-01", "body": "Soon"}]},
            },
        }
        r = run("--type", "jira", "--base-url", self.base, "fetch", "SHOP-1", env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        t = json.loads(r.stdout)
        self.assertEqual(t["title"], "Add 2FA")
        self.assertEqual(t["type"], "Story")
        self.assertEqual(t["acceptance_criteria"], ["OTP sent by SMS", "Code expires in 5 min"])
        self.assertEqual(t["url"], f"{self.base}/browse/SHOP-1")
        self.assertTrue(MockApi.calls[0][3].startswith("Basic "))

    def test_bearer_without_email_and_comment(self):
        MockApi.routes[("POST", "/rest/api/2/issue/SHOP-1/comment")] = {}
        r = run("--type", "jira", "--base-url", self.base, "comment", "SHOP-1", stdin="MR opened",
                env={"JIRA_API_TOKEN": "pat", "JIRA_EMAIL": ""})
        self.assertEqual(r.returncode, 0, r.stderr)
        method, _, body, auth = MockApi.calls[0]
        self.assertEqual(auth, "Bearer pat")
        self.assertEqual(json.loads(body), {"body": "MR opened"})

    def test_transition_by_target_status_name(self):
        MockApi.routes[("GET", "/rest/api/2/issue/SHOP-1/transitions")] = {
            "transitions": [{"id": "11", "name": "Start", "to": {"name": "In Progress"}},
                            {"id": "21", "name": "Send to review", "to": {"name": "In Review"}}]}
        MockApi.routes[("POST", "/rest/api/2/issue/SHOP-1/transitions")] = {}
        r = run("--type", "jira", "--base-url", self.base, "transition", "SHOP-1", "In Review", env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(MockApi.calls[-1][2]), {"transition": {"id": "21"}})

    def test_unknown_transition_lists_options(self):
        MockApi.routes[("GET", "/rest/api/2/issue/SHOP-1/transitions")] = {
            "transitions": [{"id": "11", "name": "Start", "to": {"name": "In Progress"}}]}
        r = run("--type", "jira", "--base-url", self.base, "transition", "SHOP-1", "Done", env=self.env)
        self.assertEqual(r.returncode, 1)
        self.assertIn("available: Start", r.stderr)

    def test_acceptance_custom_field_adf_and_comment_cap(self):
        MockApi.routes[("GET", "/rest/api/2/issue/SHOP-2")] = {
            "key": "SHOP-2",
            "fields": {
                "summary": "S", "description": "no criteria here",
                "customfield_10042": {"type": "doc", "content": [{"type": "bulletList", "content": [
                    {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "A works"}]}]},
                    {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "B works"}]}]},
                ]}]},
                "comment": {"comments": [{"body": f"c{i}"} for i in range(30)]},
            },
        }
        r = run("--type", "jira", "--base-url", self.base, "--acceptance-field", "customfield_10042",
                "--max-comments", "3", "fetch", "SHOP-2", env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        t = json.loads(r.stdout)
        self.assertEqual(t["acceptance_criteria"], ["A works", "B works"])
        self.assertEqual([c["body"] for c in t["comments"]], ["c27", "c28", "c29"])
        self.assertIn("customfield_10042", MockApi.calls[0][1])

    def test_retries_rate_limit(self):
        MockApi.routes[("GET", "/rest/api/2/issue/SHOP-3")] = [(429, None), (200, {"key": "SHOP-3", "fields": {"summary": "ok"}})]
        r = run("--type", "jira", "--base-url", self.base, "fetch", "SHOP-3", env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["title"], "ok")

    def test_html_login_page_is_a_clear_error(self):
        MockApi.routes[("GET", "/rest/api/2/issue/SHOP-4")] = b"<html>Log in</html>"
        r = run("--type", "jira", "--base-url", self.base, "fetch", "SHOP-4", env=self.env)
        self.assertEqual(r.returncode, 1)
        self.assertIn("non-JSON", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_missing_token(self):
        r = run("--type", "jira", "--base-url", self.base, "fetch", "SHOP-1", env={"JIRA_API_TOKEN": ""})
        self.assertEqual(r.returncode, 1)
        self.assertIn("JIRA_API_TOKEN", r.stderr)


class TrelloTest(HttpCase):
    def env(self):
        return {"TRELLO_API_KEY": "k", "TRELLO_TOKEN": "t", "TRELLO_API_BASE": self.base}

    def test_fetch_from_url_with_checklist(self):
        MockApi.routes[("GET", "/1/cards/AbC123")] = {
            "shortLink": "AbC123", "name": "Fix cart total", "desc": "Rounding is off.",
            "url": "https://trello.com/c/AbC123/7-fix-cart-total", "labels": [{"name": "bug"}],
            "list": {"name": "Doing"},
            "checklists": [{"checkItems": [{"name": "Totals round half-up"}]}],
            "actions": [{"memberCreator": {"fullName": "QA"}, "date": "2026-09-02", "data": {"text": "Repro attached"}}],
        }
        r = run("--type", "trello", "fetch", "https://trello.com/c/AbC123/7-fix-cart-total", env=self.env())
        self.assertEqual(r.returncode, 0, r.stderr)
        t = json.loads(r.stdout)
        self.assertEqual((t["key"], t["status"]), ("AbC123", "Doing"))
        self.assertEqual(t["acceptance_criteria"], ["Totals round half-up"])
        self.assertEqual(t["comments"][0]["body"], "Repro attached")
        self.assertIn('oauth_token="t"', MockApi.calls[0][3])
        self.assertNotIn("token=", MockApi.calls[0][1])

    def test_comment_sent_in_body_not_url(self):
        MockApi.routes[("POST", "/1/cards/AbC123/actions/comments")] = {}
        r = run("--type", "trello", "comment", "AbC123", stdin="long " * 500, env=self.env())
        self.assertEqual(r.returncode, 0, r.stderr)
        method, path, body, _ = MockApi.calls[0]
        self.assertNotIn("text=", path)
        self.assertEqual(json.loads(body)["text"].strip(), ("long " * 500).strip())

    def test_transition_moves_to_named_list(self):
        MockApi.routes[("GET", "/1/cards/AbC123")] = {"idBoard": "B1"}
        MockApi.routes[("GET", "/1/boards/B1/lists")] = [{"id": "L1", "name": "Doing"}, {"id": "L2", "name": "Review"}]
        MockApi.routes[("PUT", "/1/cards/AbC123")] = {}
        r = run("--type", "trello", "transition", "AbC123", "review", env=self.env())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("idList=L2", MockApi.calls[-1][1])


class MarkdownTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "backlog").mkdir()
        (self.root / "backlog" / "task1.md").write_text(textwrap.dedent("""\
            ---
            id: T-1
            status: todo
            priority: high
            labels: [api, auth]
            ---
            # Add login rate limiting

            Limit failed logins.

            ## Acceptance criteria
            - [ ] 5 failures lock for 15 minutes
            - [ ] Lockout is logged

            ## Notes
            - not a criterion
            """))
        (self.root / "backlog" / "task2.md").write_text("# Plain task\n\nNo frontmatter here.\n")

    def tearDown(self):
        self.tmp.cleanup()

    def md(self, *args, stdin=None):
        return run("--type", "markdown", "--root", str(self.root), "--path", "backlog", *args, stdin=stdin)

    def test_fetch_by_stem_and_id(self):
        for key in ("task1", "T-1", "task1.md"):
            r = self.md("fetch", key)
            self.assertEqual(r.returncode, 0, r.stderr)
            t = json.loads(r.stdout)
            self.assertEqual(t["title"], "Add login rate limiting")
            self.assertEqual(t["labels"], ["api", "auth"])
            self.assertEqual(t["acceptance_criteria"], ["5 failures lock for 15 minutes", "Lockout is logged"])

    def test_comment_and_transition(self):
        self.assertEqual(self.md("comment", "task1", stdin="Plan approved\nMR: !12").returncode, 0)
        self.assertEqual(self.md("transition", "task1", "in-review").returncode, 0)
        self.assertEqual(self.md("transition", "task2", "done").returncode, 0)
        text1 = (self.root / "backlog" / "task1.md").read_text()
        self.assertIn("status: in-review", text1)
        self.assertIn("## Activity", text1)
        self.assertIn("Plan approved\n  MR: !12", text1)
        self.assertEqual(self.md("comment", "task1", stdin="Done\n\nTests: ok").returncode, 0)
        text1 = (self.root / "backlog" / "task1.md").read_text()
        self.assertIn("Done\n\n  Tests: ok", text1)
        self.assertNotIn(" \n", text1)
        self.assertTrue((self.root / "backlog" / "task2.md").read_text().startswith("---\nstatus: done\n---"))

    def test_rejects_files_outside_task_dir(self):
        outside = self.root / "secret.md"
        outside.write_text("# secret\n")
        for key in (str(outside), "../secret.md", "../secret"):
            r = self.md("fetch", key)
            self.assertEqual(r.returncode, 1, key)
        r = self.md("comment", str(outside), stdin="x")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(outside.read_text(), "# secret\n")

    def test_status_with_backslash(self):
        self.assertEqual(self.md("transition", "task1", "a\\1").returncode, 0)
        self.assertIn("status: a\\1", (self.root / "backlog" / "task1.md").read_text())

    def test_missing_task(self):
        r = self.md("fetch", "task9")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no task file", r.stderr)


class CustomTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        script = self.root / "fake-tracker.py"
        script.write_text(textwrap.dedent("""\
            import json, sys
            op, key = sys.argv[1], sys.argv[2]
            if op == "fetch":
                print(json.dumps({"key": key, "title": "From in-house tracker",
                                  "description": "Acceptance criteria\\n- Works", "status": "Open"}))
            elif op == "comment":
                open("comments.log", "a").write(key + ":" + sys.stdin.read())
            elif op == "move":
                open("moves.log", "a").write(key + ":" + sys.argv[3])
            """))
        self.args = ["--type", "custom", "--root", str(self.root),
                     "--fetch-cmd", f"{sys.executable} {script} fetch {{key}}",
                     "--comment-cmd", f"{sys.executable} {script} comment {{key}}",
                     "--transition-cmd", f"{sys.executable} {script} move {{key}} {{status}}"]

    def tearDown(self):
        self.tmp.cleanup()

    def test_round_trip(self):
        r = run(*self.args, "fetch", "OTM-42")
        self.assertEqual(r.returncode, 0, r.stderr)
        t = json.loads(r.stdout)
        self.assertEqual((t["title"], t["source"]), ("From in-house tracker", "custom"))
        self.assertEqual(t["acceptance_criteria"], ["Works"])
        self.assertEqual(run(*self.args, "comment", "OTM-42", stdin="hello").returncode, 0)
        self.assertEqual(run(*self.args, "transition", "OTM-42", "In Review").returncode, 0)
        self.assertEqual((self.root / "comments.log").read_text(), "OTM-42:hello")
        self.assertEqual((self.root / "moves.log").read_text(), "OTM-42:In Review")

    def test_literal_braces_and_non_object_json(self):
        echo = self.root / "echo_args.py"
        echo.write_text("import sys\nprint(sys.argv[1] if sys.argv[2] == 'x' else '[1, 2]')\n")
        args = ["--type", "custom", "--root", str(self.root),
                "--fetch-cmd", f"{sys.executable} {echo} '{{\"a\": 1}}' {{key}}"]
        r = run(*args, "fetch", "x")          # template with literal braces; output is a JSON object
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["title"], "x")
        r = run(*args, "fetch", "OTM-1")      # output is JSON but not an object -> treated as text
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["description"], "[1, 2]")

    def test_key_cannot_inject_shell(self):
        r = run(*self.args, "fetch", "X; rm -rf /")
        self.assertEqual(r.returncode, 65)


class GitHubTest(unittest.TestCase):
    def test_rejects_non_numeric_key(self):
        r = run("--type", "github", "--repo", "o/r", "fetch", "abc")
        self.assertEqual(r.returncode, 1)
        self.assertIn("must end in a number", r.stderr)


if __name__ == "__main__":
    unittest.main()
