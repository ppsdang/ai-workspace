"""Tests for hooks/guard.py. Run: python3 -m unittest discover tests"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUARD = ROOT / "hooks" / "guard.py"


def git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


class GuardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        ws = Path(cls.tmp.name).resolve()
        cls.ws = ws
        (ws / "workspace.yaml").write_text("version: 1\nprotected_branches:\n  - main\n  - prod\n  - \"release/*\"\n")
        for name, branch in (("api", "main"), ("web", "feature/x")):
            repo = ws / "codebase" / name
            repo.mkdir(parents=True)
            git("init", "-q", "-b", "main", cwd=repo)
            git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "i", cwd=repo)
            if branch != "main":
                git("switch", "-q", "-c", branch, cwd=repo)
        git("config", "alias.p", "push", cwd=ws / "codebase" / "web")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def decide(self, command, cwd=None, raw=None):
        payload = raw if raw is not None else json.dumps(
            {"tool_input": {"command": command}, "cwd": str(cwd or self.ws)})
        r = subprocess.run([sys.executable, str(GUARD)], input=payload, capture_output=True, text=True, timeout=10)
        self.assertEqual(r.returncode, 0, r.stderr)
        if not r.stdout.strip():
            return "none"
        return json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"]

    def assertDecision(self, expected, commands, **kw):
        for c in commands:
            with self.subTest(command=c):
                self.assertEqual(self.decide(c, **kw), expected)

    def test_unrelated_commands_pass(self):
        self.assertDecision("none", [
            "ls -la", "git -C codebase/web status", "git commit -m 'push fix'", "npm test",
            "git -C codebase/web log --oneline -5", "echo push",
        ])

    def test_force_and_destructive_push_denied(self):
        self.assertDecision("deny", [
            "git -C codebase/web push --force origin feature/x",
            'git -C codebase/web push "--force" origin feature/x',
            "git -C codebase/web push -f origin feature/x",
            "git -C codebase/web push -uf origin feature/x",
            "git -C codebase/web push --force-with-lease origin feature/x",
            "git -C codebase/web push --force-with-lease=feature/x origin feature/x",
            "git -C codebase/web push origin +feature/x",
            'git -C codebase/web push origin "+feature/x"',
            "git -C codebase/web push origin :old-branch",
            "git -C codebase/web push --delete origin old",
            "git -C codebase/web push --prune origin",
            "git -C codebase/web push --all origin",
            "git -C codebase/web push --mirror origin",
        ])

    def test_protected_targets_denied(self):
        self.assertDecision("deny", [
            "git -C codebase/web push origin main",
            "git -C codebase/web push origin 'main'",
            'git -C codebase/web push origin ma""in',
            "git -C codebase/web push origin Main",
            "git -C codebase/web push origin HEAD:release/1.2",
            "git -C codebase/web push origin feature/x:refs/heads/prod",
            "git -C codebase/api push",
            "git -C codebase/api push -o ci.skip origin",
            "git -C codebase/api push origin HEAD",
            "cd codebase/api && git push",
            "cd codebase/api; git push origin",
            "/usr/bin/git -C codebase/web push origin main",
            "env GIT_TRACE=1 git -C codebase/web push origin main",
            "FOO=1 git -C codebase/web push origin main",
            'sh -c "git -C codebase/web push origin main"',
            "bash -c 'cd codebase/api && git push'",
            "(git -C codebase/web push origin main)",
            "git -C codebase/web push origin prod",
            "git -C codebase/web push -o merge_request.create origin main",
        ])

    def test_merges_denied(self):
        self.assertDecision("deny", ["gh pr merge 12 --squash", "cd codebase/web && glab mr merge 3"])

    def test_outward_actions_ask(self):
        self.assertDecision("ask", [
            "git -C codebase/web push -u origin feature/x",
            "cd codebase/web && gh pr create --base main --head feature/x --title t --body-file b.md",
            "glab mr create --source-branch feature/x --target-branch main --yes",
            "git -C codebase/web push -u origin feature/x -o merge_request.create -o merge_request.target=main "
            "-o merge_request.title=\"T-1: fix\"",
            "python3 /p/scripts/tracker.py --type jira --base-url https://x fetch A-1 && "
            "python3 /p/scripts/tracker.py --type jira --base-url https://x comment A-1",
            "python3 /p/scripts/tracker.py --type trello transition AbC Review",
        ])

    def test_api_writes_and_review_replies_ask(self):
        self.assertDecision("ask", [
            "gh api repos/o/r/issues/1/comments -f body=hi",
            "gh api -X PATCH repos/o/r/pulls/1 -f title=x",
            "gh api graphql -f query='mutation { addComment(input:{}) { clientMutationId } }'",
            "glab api --method POST projects/1/merge_requests/2/notes -f body=hi",
            "glab api -X DELETE projects/1/merge_requests/2",
            "python3 /p/scripts/review_threads.py reply https://github.com/o/r/pull/1 T_abc",
            "( cd codebase/web && gh run rerun 123 --failed )",
            "glab ci retry 456",
            "python3 /p/scripts/ci.py --provider jenkins --url https://j rerun --job a/b --branch x",
        ])
        self.assertDecision("none", [
            "gh api repos/o/r/pulls/1",
            "gh api -X GET search/issues -f q=repo:o/r",
            "gh api graphql -f query='query { viewer { login } }'",
            "glab api projects/1/merge_requests/2/discussions",
            "python3 /p/scripts/review_threads.py list https://github.com/o/r/pull/1",
            "python3 /p/scripts/review_threads.py checks https://github.com/o/r/pull/1",
            "( cd codebase/web && gh run view --job 9 --log-failed ) | tail -150",
            "glab ci trace 456",
            "python3 /p/scripts/ci.py --provider jenkins --url https://j status --job a/b --branch x",
            "git -C codebase/web merge --ff-only feature/x",
        ])

    def test_markdown_tracker_and_fetch_are_not_outward(self):
        self.assertDecision("none", [
            "python3 /p/scripts/tracker.py --type markdown --path backlog comment task1",
            "python3 /p/scripts/tracker.py --type jira --base-url https://x fetch A-1",
            "gh pr view 12", "glab mr list",
        ])

    def test_unanalysable_push_asks(self):
        self.assertDecision("ask", [
            "$(echo git) push origin main",
            "g=git; $g push origin main",
            "eval 'git push origin main'",
            "git -c alias.p=push p origin main",
            "git config alias.q push && git q origin main",
            "git -C codebase/web p origin feature/x",
            "git -C codebase/web reset --hard HEAD~1",
            "git -C codebase/web clean -fd",
            "git -C codebase/web branch -D feature/y",
        ])

    def test_heredoc_body_is_data(self):
        cmd = ("python3 /p/scripts/tracker.py --type markdown --path backlog comment task1 <<'MSG'\n"
               "Next: git push origin main --force after review\nMSG")
        self.assertEqual(self.decide(cmd), "none")
        cmd2 = "cat > notes.txt <<EOF\ngit push -f\nEOF\ngit -C codebase/web push origin main"
        self.assertEqual(self.decide(cmd2), "deny")

    def test_relative_or_missing_cwd_does_not_hang(self):
        self.assertIn(self.decide("git push origin main", cwd="relative/dir"), ("deny", "ask"))
        self.assertEqual(self.decide("", raw='{"tool_input":{"command":"ls"}}'), "none")

    def test_bad_input(self):
        self.assertEqual(self.decide("", raw="not json git push"), "ask")
        self.assertEqual(self.decide("", raw="not json"), "none")

    def test_unparseable_protected_list_asks(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "workspace.yaml").write_text("protected_branches: \n  oops: 1\n")
            self.assertEqual(self.decide("git status", cwd=d), "ask")

    def test_confirm_outward_can_be_disabled(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "workspace.yaml").write_text("guard:\n  confirm_outward: false\n")
            self.assertEqual(self.decide("gh pr create --title t", cwd=d), "none")
            self.assertEqual(self.decide("gh pr merge 1", cwd=d), "deny")


if __name__ == "__main__":
    unittest.main()
