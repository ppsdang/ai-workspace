"""Tests for scripts/parse_repos.py: whatever users paste becomes a clean repository list."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "parse_repos.py"


def parse(text, existing=""):
    r = subprocess.run([sys.executable, str(SCRIPT), "--existing", existing], input=text,
                       capture_output=True, text=True)
    return r.returncode, json.loads(r.stdout)


class ParseReposTest(unittest.TestCase):
    def test_one_link(self):
        code, repos = parse("git@gitlab.oodleslab.com:payroll/backend.git")
        self.assertEqual((code, repos), (0, [{"name": "backend", "url": "git@gitlab.oodleslab.com:payroll/backend.git"}]))

    def test_many_links_any_separator(self):
        text = """git@gitlab.example.com:payroll/backend.git, https://gitlab.example.com/payroll/frontend.git
        ssh://git@gitlab.example.com:2222/payroll/mobile-app.git ; https://github.com/acme/Docs-Site"""
        code, repos = parse(text)
        self.assertEqual([r["name"] for r in repos], ["backend", "frontend", "mobile-app", "docs-site"])

    def test_links_inside_prose_and_markdown(self):
        text = "Our repos are `git@gitlab.example.com:shop/api.git` and [web](https://gitlab.example.com/shop/web.git)."
        code, repos = parse(text)
        self.assertEqual([r["url"] for r in repos],
                         ["git@gitlab.example.com:shop/api.git", "https://gitlab.example.com/shop/web.git"])

    def test_prose_words_are_not_names(self):
        text = ("Here are our repos: git@gitlab.oodleslab.com:payroll/backend.git, "
                "https://gitlab.oodleslab.com/payroll/frontend.git and also git@gitlab.oodleslab.com:payroll/mobile-app.git")
        code, repos = parse(text)
        self.assertEqual([r["name"] for r in repos], ["backend", "frontend", "mobile-app"])
        code, repos = parse("repos: git@h:a/api.git plus git@h:a/web.git")
        self.assertEqual([r["name"] for r in repos], ["api", "web"])

    def test_explicit_names_still_work(self):
        code, repos = parse("server git@h:acme/backend.git\nclient git@h:acme/frontend.git")
        self.assertEqual([r["name"] for r in repos], ["server", "client"])
        code, repos = parse("- server git@h:acme/backend.git\n2. client git@h:acme/frontend.git")
        self.assertEqual([r["name"] for r in repos], ["server", "client"])
        code, repos = parse("server git@h:acme/backend.git, client git@h:acme/frontend.git")
        self.assertEqual([r["name"] for r in repos], ["server", "client"])

    def test_name_clashes_use_the_group(self):
        code, repos = parse("git@h:payroll/api.git git@h:billing/api.git")
        self.assertEqual([r["name"] for r in repos], ["payroll-api", "billing-api"])
        code, repos = parse("git@h:shop/api.git", existing="api")
        self.assertEqual(repos[0]["name"], "shop-api")

    def test_duplicates_and_noise(self):
        code, repos = parse("git@h:a/b.git git@h:a/b.git see https:// and /not/a/folder")
        self.assertEqual(len(repos), 1)

    def test_local_folders_only_if_they_exist(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "my-service"
            repo.mkdir()
            code, repos = parse(f"{repo} /definitely/missing/path")
            self.assertEqual(repos, [{"name": "my-service", "url": str(repo)}])

    def test_windows_paths(self):
        import os
        sys.path.insert(0, str(SCRIPT.parent))
        import parse_repos
        self.assertEqual(parse_repos.split_link(r"C:\Users\me\code\billing-api"), ("code", "billing-api"))
        self.assertEqual(parse_repos.split_link("C:/Users/me/code/web.git"), ("code", "web"))
        link = parse_repos.LINK.search(r"use C:\Users\me\code\api please").group("link")
        self.assertEqual(link, r"C:\Users\me\code\api")
        if os.name == "nt":
            with tempfile.TemporaryDirectory() as d:
                code, repos = parse(str(Path(d)))
                self.assertEqual(len(repos), 1)

    def test_nothing_found(self):
        code, repos = parse("not sure yet")
        self.assertEqual((code, repos), (2, []))


if __name__ == "__main__":
    unittest.main()
