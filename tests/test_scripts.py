"""Tests for scripts/clone-repo.sh and scripts/status.sh. Run: python3 -m unittest discover tests"""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLONE = ROOT / "scripts" / "clone-repo.sh"
STATUS = ROOT / "scripts" / "status.sh"
BASH = shutil.which("bash")


def sh(*args, cwd=None):
    return subprocess.run([BASH, *map(str, args)], capture_output=True, text=True, cwd=cwd)


def git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@unittest.skipUnless(BASH, "bash not available")
class CloneTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.src = self.root / "src"
        self.src.mkdir()
        git("init", "-q", "-b", "main", cwd=self.src)
        git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "one", cwd=self.src)
        self.ws = self.root / "ws"

    def tearDown(self):
        self.tmp.cleanup()

    def test_clone_then_update_fast_forwards_base(self):
        r = sh(CLONE, self.ws, "api", self.src)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("cloned: api (main)", r.stdout)
        git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "two", cwd=self.src)
        r = sh(CLONE, self.ws, "api", str(self.src) + "/", "main")
        self.assertEqual(r.returncode, 0, r.stderr)
        log = subprocess.run(["git", "-C", self.ws / "codebase" / "api", "log", "--oneline"],
                             capture_output=True, text=True).stdout
        self.assertIn("two", log)

    def test_rejects_bad_names_and_option_urls(self):
        for name in (".", "..", "a/b", "x y"):
            self.assertEqual(sh(CLONE, self.ws, name, self.src).returncode, 65, name)
        self.assertEqual(sh(CLONE, self.ws, "api", "--upload-pack=touch /tmp/pwned").returncode, 65)
        self.assertEqual(sh(CLONE, self.ws, "api", self.src, "--foo").returncode, 65)

    def test_remote_mismatch_detected_but_equivalent_urls_accepted(self):
        dest = self.ws / "codebase" / "svc"
        dest.mkdir(parents=True)
        git("init", "-q", cwd=dest)
        git("remote", "add", "origin", "git@github.com:Acme/svc.git", cwd=dest)
        for equivalent in ("https://github.com/acme/svc", "ssh://git@github.com:22/acme/svc.git"):
            r = sh(CLONE, self.ws, "svc", equivalent)
            self.assertNotIn("exists with remote", r.stderr, equivalent)
        r = sh(CLONE, self.ws, "svc", "https://github.com/acme/other")
        self.assertEqual(r.returncode, 1)
        self.assertIn("exists with remote", r.stderr)


@unittest.skipUnless(BASH, "bash not available")
class StatusTest(unittest.TestCase):
    def test_broken_repo_does_not_abort_table(self):
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            good = ws / "codebase" / "good"
            good.mkdir(parents=True)
            git("init", "-q", "-b", "main", cwd=good)
            broken = ws / "codebase" / "broken"
            (broken / ".git").mkdir(parents=True)
            r = sh(STATUS, ws)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("codebase/good", r.stdout)
            self.assertIn("codebase/broken", r.stdout)
            self.assertIn("error", r.stdout)

    def test_single_repo_mode_and_worktrees(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            git("init", "-q", "-b", "main", cwd=repo)
            r = sh(STATUS, repo, ".")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertRegex(r.stdout, r"\n\.\s+main")


@unittest.skipUnless(BASH, "bash not available")
class ExcludeLocalTest(unittest.TestCase):
    def test_idempotent_and_effective(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            git("init", "-q", "-b", "main", cwd=repo)
            (repo / "workspace.yaml").write_text("x")
            (repo / "context").mkdir()
            (repo / "context" / "p.md").write_text("x")
            for _ in range(2):
                r = sh(ROOT / "scripts" / "exclude-local.sh", repo, "/workspace.yaml", "/context/")
                self.assertEqual(r.returncode, 0, r.stderr)
            text = (repo / ".git" / "info" / "exclude").read_text()
            self.assertEqual(text.count("/workspace.yaml"), 1)
            status = subprocess.run(["git", "-C", repo, "status", "--porcelain"], capture_output=True, text=True).stdout
            self.assertEqual(status, "")


@unittest.skipUnless(BASH, "bash not available")
class WorktreeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name).resolve()
        self.root = root
        self.origin = root / "origin.git"
        git("init", "-q", "--bare", "-b", "main", str(self.origin), cwd=root)
        self.clone = root / "ws" / "codebase" / "api"
        git("clone", "-q", str(self.origin), str(self.clone), cwd=root)
        git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "i", cwd=self.clone)
        git("push", "-q", "origin", "main", cwd=self.clone)
        self.dest = root / "ws" / "work" / "T-1" / "api"

    def tearDown(self):
        self.tmp.cleanup()

    def wt(self, *args):
        return sh(ROOT / "scripts" / "worktree.sh", *args)

    def test_add_reuse_and_guarded_remove(self):
        r = self.wt("add", self.clone, self.dest, "feature/T-1-x", "main")
        self.assertEqual(r.returncode, 0, r.stderr)
        branch = subprocess.run(["git", "-C", self.dest, "rev-parse", "--abbrev-ref", "HEAD"],
                                capture_output=True, text=True).stdout.strip()
        self.assertEqual(branch, "feature/T-1-x")
        upstream = subprocess.run(["git", "-C", self.dest, "rev-parse", "--abbrev-ref", "@{u}"],
                                  capture_output=True, text=True)
        self.assertNotEqual(upstream.returncode, 0, "worktree branch must not track the base")
        self.assertIn("reused", self.wt("add", self.clone, self.dest, "feature/T-1-x", "main").stdout)
        self.assertEqual(self.wt("add", self.clone, self.dest, "other", "main").returncode, 1)

        (self.dest / "f.txt").write_text("x")
        self.assertIn("uncommitted", self.wt("remove", self.clone, self.dest).stderr)
        git("add", "f.txt", cwd=self.dest)
        git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "f", cwd=self.dest)
        self.assertIn("not pushed", self.wt("remove", self.clone, self.dest).stderr)
        git("push", "-q", "-u", "origin", "feature/T-1-x", cwd=self.dest)
        r = self.wt("remove", self.clone, self.dest)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(self.dest.exists())

    def test_rejects_bad_arguments(self):
        self.assertEqual(self.wt("add", self.clone, self.dest, "--evil", "main").returncode, 1)
        self.assertEqual(self.wt("add", self.clone, self.dest, "bad..name", "main").returncode, 1)


if __name__ == "__main__":
    unittest.main()
