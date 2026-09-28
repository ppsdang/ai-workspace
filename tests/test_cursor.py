"""Cursor support: hook formats, plugin manifests. Run: python3 -m unittest discover tests"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUARD = ROOT / "hooks" / "guard.py"
SESSION = ROOT / "hooks" / "session_start.py"


def run(script, payload, *args):
    r = subprocess.run([sys.executable, str(script), *args], input=payload, capture_output=True, text=True, timeout=10)
    return r.returncode, r.stdout.strip()


class CursorGuardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.ws = Path(cls.tmp.name).resolve()
        (cls.ws / "workspace.yaml").write_text("version: 1\nprotected_branches: [main]\n")
        repo = cls.ws / "codebase" / "api"
        repo.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def decide(self, command, *args):
        payload = json.dumps({"command": command, "cwd": str(self.ws), "sandbox": False,
                              "conversation_id": "c", "generation_id": "g"})
        code, out = run(GUARD, payload, *args)
        self.assertEqual(code, 0)
        return json.loads(out)  # Cursor mode must always answer with JSON

    def test_every_answer_is_explicit(self):
        self.assertEqual(self.decide("ls -la"), {"permission": "allow"})
        deny = self.decide("git -C codebase/api push --force origin feature/x")
        self.assertEqual(deny["permission"], "deny")
        self.assertIn("not allowed", deny["agent_message"])
        self.assertEqual(deny["user_message"], deny["agent_message"])
        ask = self.decide("git -C codebase/api push -u origin feature/x")
        self.assertEqual(ask["permission"], "ask")

    def test_detected_without_flag_and_explicit_flag(self):
        self.assertEqual(self.decide("git -C codebase/api push origin main")["permission"], "deny")
        self.assertEqual(self.decide("echo hi", "--format", "cursor"), {"permission": "allow"})

    def test_bad_input_still_answers(self):
        code, out = run(GUARD, "garbage", "--format", "cursor")
        self.assertEqual(json.loads(out), {"permission": "allow"})
        code, out = run(GUARD, "garbage git push", "--format", "cursor")
        self.assertEqual(json.loads(out)["permission"], "ask")

    def test_claude_format_unchanged(self):
        code, out = run(GUARD, json.dumps({"tool_input": {"command": "ls"}, "cwd": str(self.ws)}))
        self.assertEqual(out, "")  # Claude Code: silence = normal permission flow


class CursorSessionStartTest(unittest.TestCase):
    def test_env_and_context(self):
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            (ws / "workspace.yaml").write_text("version: 1\n")
            (ws / "tasks" / "T-1").mkdir(parents=True)
            (ws / "tasks" / "T-1" / "state.md").write_text("---\nkey: T-1\nphase: implement\n---\n")
            code, out = run(SESSION, json.dumps({"session_id": "s", "cwd": d}), "--format", "cursor")
            data = json.loads(out)
            self.assertEqual(Path(data["env"]["AI_WORKSPACE_PLUGIN_ROOT"]), ROOT)
            self.assertIn("T-1: implement", data["additional_context"])
        code, out = run(SESSION, json.dumps({"session_id": "s", "cwd": "/"}), "--format", "cursor")
        self.assertEqual(set(json.loads(out)), {"env"})  # outside a workspace: only the plugin path


class CursorDoctorTest(unittest.TestCase):
    def test_expected_files_follow_tools(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "workspace.yaml").write_text("version: 1\n")
            doctor = ROOT / "scripts" / "doctor.py"
            out = subprocess.run([sys.executable, str(doctor), "--root", d, "--tools", "cursor"],
                                 capture_output=True, text=True).stdout
            self.assertIn("AGENTS.md", out)
            self.assertNotIn("CLAUDE.md", out)
            out = subprocess.run([sys.executable, str(doctor), "--root", d, "--tools", "claude-code,cursor"],
                                 capture_output=True, text=True).stdout
            self.assertIn("AGENTS.md", out)
            self.assertIn("CLAUDE.md", out)


class EmptyWorkspaceTest(unittest.TestCase):
    def test_doctor_explains_missing_codebases(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "workspace.yaml").write_text("version: 1\ncodebases: []\n")
            out = subprocess.run([sys.executable, str(ROOT / "scripts" / "doctor.py"), "--root", d],
                                 capture_output=True, text=True).stdout
            self.assertRegex(out, r"WARN\s+codebases\s+none yet")


class CursorManifestTest(unittest.TestCase):
    def test_manifests_and_hooks(self):
        plugin = json.loads((ROOT / ".cursor-plugin" / "plugin.json").read_text(encoding="utf-8"))
        claude = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(plugin["name"], claude["name"])
        self.assertEqual(plugin["version"], claude["version"], "keep both manifests on the same version")
        # Cursor must not auto-discover hooks/hooks.json, which is in Claude Code's format
        self.assertEqual(plugin["hooks"], "cursor/hooks.json")
        hooks = json.loads((ROOT / plugin["hooks"]).read_text(encoding="utf-8"))["hooks"]
        self.assertEqual(set(hooks), {"beforeShellExecution", "sessionStart"})
        for entries in hooks.values():
            for entry in entries:
                script = entry["command"].split('"')[1].replace("${CURSOR_PLUGIN_ROOT}", str(ROOT))
                self.assertTrue(Path(script).is_file(), script)
                self.assertIn("--format cursor", entry["command"])
        market = json.loads((ROOT / ".cursor-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        self.assertEqual(market["plugins"][0]["name"], plugin["name"])
        for skill in ROOT.glob("skills/*/SKILL.md"):
            text = skill.read_text(encoding="utf-8")
            self.assertIn("AI_WORKSPACE_PLUGIN_ROOT", text, f"{skill} lacks the Cursor path fallback")


if __name__ == "__main__":
    unittest.main()
