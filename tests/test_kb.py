"""Tests for scripts/kb.py: indexing, search (FTS5 and fallback), INDEX.md, staleness, checks."""
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

KB = Path(__file__).resolve().parent.parent / "scripts" / "kb.py"


def git(*args, cwd):
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args], cwd=cwd, check=True,
                   capture_output=True)


def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text), encoding="utf-8")


class KBCase(unittest.TestCase):
    env = {}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        (self.ws / "workspace.yaml").write_text("version: 1\n")
        write(self.ws / "context/product/overview.md", """\
            ---
            title: Payroll product overview
            kind: overview
            summary: Payroll SaaS for small companies; payslips, tax filing, employee portal.
            tags: [payroll]
            ---
            # Payroll product overview

            ## Users
            HR managers run payroll; employees download payslips.

            ## Glossary
            - **Gross pay**: pay before deductions.
            """)
        write(self.ws / "context/product/features/payslips.md", """\
            ---
            title: Payslip generation
            kind: feature
            summary: Monthly payslip PDFs with tax and deductions.
            tags: [payslip, tax, pdf]
            codebases: [backend, frontend]
            sources: ["backend:src/payslip/"]
            ---
            # Payslip generation

            ## How it works
            The backend computes gross pay, income tax and social contributions, then renders a PDF.

            ## Where
            - backend: src/payslip/generator.py
            """)
        write(self.ws / "context/decisions/0001-pdf-library.md", """\
            ---
            title: Use WeasyPrint for PDFs
            kind: decision
            summary: Chose WeasyPrint over wkhtmltopdf for payslip PDFs (maintained, no binary).
            ---
            # Use WeasyPrint for PDFs
            Context: payslip rendering needed CSS support.
            """)

    def tearDown(self):
        self.tmp.cleanup()

    def kb(self, *args):
        r = subprocess.run([sys.executable, str(KB), "--root", str(self.ws), *args], capture_output=True,
                           text=True, env={**os.environ, **self.env})
        return r.returncode, r.stdout, r.stderr


class SearchTest(KBCase):
    def test_index_and_rank(self):
        code, out, err = self.kb("index")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["documents"], 3)
        code, out, _ = self.kb("search", "how is income tax on payslips calculated")
        results = json.loads(out)
        self.assertEqual(results[0]["path"], "context/product/features/payslips.md")
        self.assertIn("income tax", results[0]["snippet"])
        code, out, _ = self.kb("search", "pdf", "--kind", "decision")
        self.assertEqual([r["path"] for r in json.loads(out)], ["context/decisions/0001-pdf-library.md"])

    def test_incremental_and_removal(self):
        self.kb("index")
        code, out, _ = self.kb("index")
        self.assertEqual(json.loads(out)["updated"], 0)
        (self.ws / "context/decisions/0001-pdf-library.md").unlink()
        code, out, _ = self.kb("index")
        self.assertEqual(json.loads(out)["removed"], 1)
        code, out, _ = self.kb("search", "weasyprint")
        self.assertEqual(json.loads(out), [])

    def test_search_reindexes_changed_docs(self):
        self.kb("index")
        p = self.ws / "context/product/features/payslips.md"
        p.write_text(p.read_text() + "\n## Bonuses\nQuarterly bonus payouts are added as a separate line.\n")
        code, out, _ = self.kb("search", "bonus payouts")
        self.assertEqual(json.loads(out)[0]["section"], "Bonuses")

    def test_no_meaningful_words(self):
        code, out, _ = self.kb("search", "how is the")
        self.assertEqual(json.loads(out), [])


class FallbackSearchTest(SearchTest):
    env = {"KB_NO_FTS": "1"}


class IndexMdTest(KBCase):
    def test_grouped_index(self):
        code, out, _ = self.kb("index-md")
        text = (self.ws / "context/INDEX.md").read_text()
        self.assertLess(text.index("## Product"), text.index("## Features"))
        self.assertIn("- [Payslip generation](product/features/payslips.md): Monthly payslip PDFs", text)
        self.assertIn("## Decisions", text)


class StaleAndCheckTest(KBCase):
    def test_stale_by_source_paths(self):
        repo = self.ws / "codebase" / "backend"
        (repo / "src/payslip").mkdir(parents=True)
        (repo / "src/other").mkdir(parents=True)
        git("init", "-q", "-b", "main", cwd=repo)
        (repo / "src/payslip/generator.py").write_text("v1\n")
        (repo / "src/other/x.py").write_text("x\n")
        git("add", "-A", cwd=repo)
        git("commit", "-qm", "one", cwd=repo)
        sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"], capture_output=True,
                             text=True).stdout.strip()
        p = self.ws / "context/product/features/payslips.md"
        p.write_text(p.read_text().replace("sources:", f"generated_from: {{ backend: {sha} }}\nsources:", 1))
        (repo / "src/other/x.py").write_text("y\n")
        git("commit", "-qam", "unrelated", cwd=repo)
        code, out, _ = self.kb("stale")
        self.assertEqual(json.loads(out), [], "changes outside the doc's sources don't make it stale")
        (repo / "src/payslip/generator.py").write_text("v2\n")
        git("commit", "-qam", "payslip change", cwd=repo)
        stale = json.loads(self.kb("stale")[1])
        self.assertEqual(stale[0]["path"], "context/product/features/payslips.md")
        self.assertEqual(stale[0]["changes"][0]["changed_files"], ["src/payslip/generator.py"])
        # compared against an explicit ref (e.g. the base branch), not the checkout
        self.assertEqual(json.loads(self.kb("stale", "--ref", f"backend={sha}")[1]), [])

    def test_check_budgets_and_frontmatter(self):
        write(self.ws / "context/product/features/huge.md", "---\ntitle: Huge\nkind: feature\nsummary: x\n---\n"
              + "line\n" * 200)
        write(self.ws / "context/notes.md", "# No frontmatter\n")
        write(self.ws / "context/features/misplaced.md", "---\ntitle: M\nkind: feature\nsummary: x\n---\n")
        code, out, _ = self.kb("check")
        self.assertEqual(code, 1)
        self.assertIn("huge.md: 205 lines, over the 150-line budget", out)
        self.assertIn("notes.md: no frontmatter", out)
        self.assertIn("misplaced.md: feature documents belong in context/product/features/", out)


class DoctorKnowledgeTest(KBCase):
    def test_reports_documents_and_gaps(self):
        doctor = KB.parent / "doctor.py"
        out = subprocess.run([sys.executable, str(doctor), "--root", str(self.ws)], capture_output=True, text=True).stdout
        self.assertIn("no context/INDEX.md yet", out)
        p = self.ws / "context/product/overview.md"
        p.write_text(p.read_text() + "\n## Features\n- Tax filing (not documented yet)\n")
        self.kb("index-md")
        out = subprocess.run([sys.executable, str(doctor), "--root", str(self.ws)], capture_output=True, text=True).stdout
        self.assertRegex(out, r"OK\s+knowledge\s+3 documents, 1 features not documented yet")


if __name__ == "__main__":
    unittest.main()
