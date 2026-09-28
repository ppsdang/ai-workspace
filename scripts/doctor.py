#!/usr/bin/env python3
"""Check that a machine and workspace are ready for ai-workspace.

  doctor.py [--root DIR] [--tracker TYPE] [--host github|gitlab|other|none] [--host-url URL]
            [--ci host|jenkins|custom|none] [--tools claude-code,cursor] [--codebases a,b=path,c]

  A codebase is `name` (cloned at codebase/<name>) or `name=path` (e.g. `shop=.` in single-repo mode).

Prints one line per check (OK / WARN / FAIL) and exits 1 if any check FAILs.
Never prints secret values; for environment variables it only reports whether they are set.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path

TRACKER_ENV = {
    "jira": (["JIRA_API_TOKEN"], ["JIRA_EMAIL"]),   # required (api mode), optional
    "trello": (["TRELLO_API_KEY", "TRELLO_TOKEN"], []),
}

results: list[tuple[str, str, str]] = []


def add(status, check, detail=""):
    results.append((status, check, detail))


def cmd(argv, timeout=15):
    try:
        r = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.SubprocessError) as e:
        return 127, str(e)


def first_line(text):
    return text.splitlines()[0] if text else ""


def check_tools(host, hostname=None):
    add("OK" if sys.version_info >= (3, 10) else "FAIL", "python", sys.version.split()[0] +
        ("" if sys.version_info >= (3, 10) else " (3.10+ required)"))
    if shutil.which("git"):
        add("OK", "git", first_line(cmd(["git", "--version"])[1]))
    else:
        add("FAIL", "git", "not installed")
    if not shutil.which("bash"):
        add("WARN", "bash", "not found; clone/status scripts need it (on Windows use Git Bash)")
    if host == "none":
        add("OK", "git host", "local only: nothing is pushed")
    if host == "other":
        add("INFO", "git host", "other host: MRs/PRs are opened by hand from the link the flow provides")
    for tool, needed in (("gh", host == "github"), ("glab", host == "gitlab")):
        if not needed and not shutil.which(tool):
            continue
        login = f"`{tool} auth login" + (f" --hostname {hostname}`" if hostname else "`")
        if not shutil.which(tool):
            if tool == "glab" and needed:
                add("WARN", tool, "not installed; MRs can still be opened via git push options, but "
                    f"descriptions, CI and review follow-up need it: install glab, then {login}")
            else:
                add("WARN" if needed else "INFO", tool, "not installed: pushes still work and you get a link to "
                    f"open the PR by hand; install it and run {login} to automate PRs, /ci and /respond")
            continue
        code, out = cmd([tool, "auth", "status", *(["--hostname", hostname] if hostname else [])])
        where = f" to {hostname}" if hostname else ""
        add("OK" if code == 0 else "WARN", f"{tool} auth",
            f"logged in{where}" if code == 0 else f"not logged in{where}: run {login}")
    if shutil.which("gitleaks"):
        add("OK", "gitleaks", "found; used by the secrets scan")


def check_ci(ci):
    if ci == "jenkins":
        for name in ("JENKINS_USER", "JENKINS_TOKEN"):
            add("OK" if os.environ.get(name) else "WARN", f"env {name}",
                "set" if os.environ.get(name) else "not set (needed by /ai-workspace:ci for Jenkins)")
    elif ci == "none":
        add("OK", "ci", "none: tests run locally in every task")


def check_tracker(tracker):
    if not tracker:
        return
    required, optional = TRACKER_ENV.get(tracker, ([], []))
    for name in required:
        add("OK" if os.environ.get(name) else "WARN", f"env {name}",
            "set" if os.environ.get(name) else f"not set (needed for {tracker} via api)")
    for name in optional:
        if not os.environ.get(name):
            add("WARN", f"env {name}", "not set (needed for Jira Cloud basic auth)")
    if tracker == "github" and not shutil.which("gh"):
        add("FAIL", "tracker github", "`gh` is required for GitHub Issues")
    if tracker in ("jira", "custom"):
        add("INFO", f"tracker {tracker}", "if it uses an MCP server, check it is connected with /mcp")


def check_workspace(root: Path, codebases, tools=("claude-code",)):
    manifest = root / "workspace.yaml"
    if not manifest.is_file():
        add("FAIL", "workspace.yaml", f"not found in {root}; run /ai-workspace:init")
        return
    add("OK", "workspace.yaml", "found")
    if not codebases and re.search(r"^codebases:\s*\[\s*\]", manifest.read_text(encoding="utf-8"), re.M):
        add("WARN", "codebases", "none yet: add them under codebases: in workspace.yaml, or run /ai-workspace:init again")
    for spec in codebases:
        name, _, path = spec.partition("=")
        repo = (root / os.path.expanduser(path)) if path else root / "codebase" / name
        if not (repo / ".git").exists():
            add("FAIL", f"codebase {name}", "not cloned; run /ai-workspace:init")
            continue
        if cmd(["git", "-C", str(repo), "remote", "get-url", "origin"])[0] != 0:
            add("OK", f"codebase {name}", "present, local only (no remote)")
        else:
            code, out = cmd(["git", "-C", str(repo), "ls-remote", "--exit-code", "--heads", "origin"], timeout=30)
            add("OK" if code == 0 else "WARN", f"codebase {name}",
                "cloned, remote reachable" if code == 0 else "cloned, remote not reachable (auth/network?)")
        profiles = root / "context" / "codebases"
        if not (profiles / f"{name}.md").is_file() and not any(profiles.glob(f"{name}--*.md")):
            add("WARN", f"profile {name}", "missing; re-run /ai-workspace:init")
    check_knowledge(root)
    single = any(spec.partition("=")[2] == "." for spec in codebases)
    expected = []
    if "claude-code" in tools:
        expected += [".claude/settings.local.json"] if single else [".claude/settings.json", "CLAUDE.md"]
    if "cursor" in tools:
        expected += [".cursor/rules/ai-workspace.mdc"] if single else ["AGENTS.md"]
    for f in expected:
        if not (root / f).is_file():
            add("WARN", f, "missing; re-run /ai-workspace:init (and approve its file writes)")


def check_knowledge(root: Path):
    ctx = root / "context"
    if not (ctx / "INDEX.md").is_file():
        add("WARN", "knowledge", "no context/INDEX.md yet: run /ai-workspace:init (after adding repositories)")
        return
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import kb
        docs = kb.documents(root)
        stale = kb.stale(root)
        undocumented = sum(t.count("(not documented yet)") for t in
                           [(ctx / "product" / "overview.md").read_text(encoding="utf-8")]
                           if (ctx / "product" / "overview.md").is_file())
    except Exception as e:  # noqa: BLE001 - a readiness check must not crash
        add("WARN", "knowledge", f"could not read the knowledge base: {e}")
        return
    add("OK" if not stale else "WARN", "knowledge",
        f"{len(docs)} documents" + (f", {len(stale)} out of date (run /ai-workspace:refresh)" if stale else "")
        + (f", {undocumented} features not documented yet (/ai-workspace:learn)" if undocumented else ""))


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".")
    p.add_argument("--tracker")
    p.add_argument("--host", choices=["github", "gitlab", "other", "none"])
    p.add_argument("--ci", choices=["host", "jenkins", "custom", "none"])
    p.add_argument("--host-url", help="self-hosted / enterprise web URL, e.g. https://gitlab.example.com")
    p.add_argument("--codebases", default="")
    p.add_argument("--tools", default="claude-code", help="comma-separated: claude-code, cursor")
    a = p.parse_args(argv)
    hostname = urllib.parse.urlsplit(a.host_url).hostname if a.host_url else None
    check_tools(a.host, hostname)
    check_ci(a.ci)
    check_tracker(a.tracker)
    check_workspace(Path(a.root).resolve(), [c for c in a.codebases.split(",") if c],
                    tuple(t.strip() for t in a.tools.split(",") if t.strip()))
    width = max(len(c) for _, c, _ in results)
    for status, check, detail in results:
        print(f"{status:<5} {check:<{width}}  {detail}")
    return 1 if any(s == "FAIL" for s, _, _ in results) else 0


if __name__ == "__main__":
    sys.exit(main())
