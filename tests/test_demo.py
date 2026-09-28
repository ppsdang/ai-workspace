"""The demo builds from scratch and its sample projects pass their own tests."""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASH = shutil.which("bash")


@unittest.skipUnless(BASH, "bash not available")
class DemoTest(unittest.TestCase):
    def test_setup_builds_remotes_and_workspace(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "demo"
            r = subprocess.run([BASH, str(ROOT / "examples/demo/setup.sh"), str(target)],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            for name in ("api", "web"):
                log = subprocess.run(["git", "-C", str(target / "remotes" / f"{name}.git"), "log", "--oneline", "main"],
                                     capture_output=True, text=True)
                self.assertIn("Initial commit", log.stdout)
            manifest = (target / "shop-workspace" / "workspace.yaml").read_text(encoding="utf-8")
            url = next(line.split("url:", 1)[1].strip() for line in manifest.splitlines() if "url:" in line)
            self.assertTrue(url.endswith("remotes/api.git"), url)  # Git Bash on Windows writes /c/... paths
            self.assertTrue((target / "shop-workspace" / "backlog" / "task2.md").is_file())
            again = subprocess.run([BASH, str(ROOT / "examples/demo/setup.sh"), str(target)], capture_output=True, text=True)
            self.assertEqual(again.returncode, 1, "must refuse to overwrite")

    def test_seed_projects_pass_their_tests(self):
        api = ROOT / "examples/demo/seeds/api"
        r = subprocess.run([sys.executable, "-m", "unittest", "discover", "tests"], cwd=api, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        for cache in api.rglob("__pycache__"):
            shutil.rmtree(cache)
        if shutil.which("node"):
            r = subprocess.run(["node", "--test"], cwd=ROOT / "examples/demo/seeds/web", capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class SchemaTest(unittest.TestCase):
    def test_schema_is_valid_json_and_covers_template_keys(self):
        schema = json.loads((ROOT / "schema/workspace.schema.json").read_text(encoding="utf-8"))
        top = set(schema["properties"])
        template = (ROOT / "templates/workspace.yaml").read_text(encoding="utf-8")
        keys = set(re.findall(r"^([a-z_]+):", template, re.M))
        self.assertLessEqual(keys, top, f"template keys missing from schema: {keys - top}")
        codebase = schema["properties"]["codebases"]["items"]["properties"]
        self.assertIn("ci_job", codebase)
        self.assertIn("ci_job", codebase["components"]["items"]["properties"])


if __name__ == "__main__":
    unittest.main()
