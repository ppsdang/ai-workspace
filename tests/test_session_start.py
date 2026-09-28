"""Tests for hooks/session_start.py. Run: python3 -m unittest discover tests"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "hooks" / "session_start.py"


def run(cwd, raw=None):
    payload = raw if raw is not None else json.dumps({"cwd": str(cwd), "hook_event_name": "SessionStart"})
    return subprocess.run([sys.executable, str(HOOK)], input=payload, capture_output=True, text=True)


class SessionStartTest(unittest.TestCase):
    def test_lists_unfinished_tasks_only(self):
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            (ws / "workspace.yaml").write_text("version: 1\n")
            for key, phase, extra in (("T-1", "done", ""), ("T-2", "shipped", ""),
                                      ("T-3", "blocked", "blocked_reason: waiting for payments API\n"),
                                      ("T-4", "implement", "")):
                (ws / "tasks" / key).mkdir(parents=True)
                (ws / "tasks" / key / "state.md").write_text(f"---\nkey: {key}\nphase: {phase}\n{extra}---\nnext\n")
            (ws / "codebase" / "api").mkdir(parents=True)
            r = run(ws / "codebase" / "api")
            self.assertEqual(r.returncode, 0)
            self.assertIn("3 unfinished task(s)", r.stdout)
            self.assertNotIn("T-1", r.stdout)
            self.assertIn("T-3: blocked; blocked (waiting for payments API)", r.stdout)
            self.assertIn("/ai-workspace:task T-4 resumes it", r.stdout)

    def test_silent_outside_workspace_and_on_bad_input(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(run(d).stdout, "")
        self.assertEqual(run(".", raw="garbage").returncode, 0)


if __name__ == "__main__":
    unittest.main()
