#!/usr/bin/env python3
"""Check that a machine and workspace are ready for ai-workspace.

  doctor.py [--root DIR] [--tracker TYPE] [--host github|gitlab] [--codebases a,b=path,c]

  A codebase is `name` (cloned at codebase/<name>) or `name=path` (e.g. `shop=.` in single-repo mode).

Prints one line per check (OK / WARN / FAIL) and exits 1 if any check FAILs.
Never prints secret values; for environment variables it only reports whether they are set.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
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


def check_tools(host):
    add("OK" if sys.version_info >= (3, 10) else "FAIL", "python", sys.version.split()[0] +
        ("" if sys.version_info >= (3, 10) else " (3.10+ required)"))
    if shutil.which("git"):
        add("OK", "git", first_line(cmd(["git", "--version"])[1]))
    else:
        add("FAIL", "git", "not installed")
    if not shutil.which("bash"):
        add("WARN", "bash", "not found; clone/status scripts need it (on Windows use Git Bash)")
    for tool, needed in (("gh", host == "github"), ("glab", host == "gitlab")):
        if not needed and not shutil.which(tool):
            continue
        if not shutil.which(tool):
            add("FAIL" if needed else "WARN", tool, "not installed; needed to open MRs/PRs")
            continue
        code, out = cmd([tool, "auth", "status"])
        add("OK" if code == 0 else ("FAIL" if needed else "WARN"), f"{tool} auth",
            "logged in" if code == 0 else f"not logged in: run `{tool} auth login`")
    if shutil.which("gitleaks"):
        add("OK", "gitleaks", "found; used by the secrets scan")


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


def check_workspace(root: Path, codebases):
    manifest = root / "workspace.yaml"
    if not manifest.is_file():
        add("FAIL", "workspace.yaml", f"not found in {root}; run /ai-workspace:init")
        return
    add("OK", "workspace.yaml", "found")
    for spec in codebases:
        name, _, path = spec.partition("=")
        repo = root / (path or f"codebase/{name}")
        if not (repo / ".git").exists():
            add("FAIL", f"codebase {name}", "not cloned; run /ai-workspace:init")
            continue
        code, out = cmd(["git", "-C", str(repo), "ls-remote", "--exit-code", "--heads", "origin"], timeout=30)
        add("OK" if code == 0 else "WARN", f"codebase {name}",
            "cloned, remote reachable" if code == 0 else "cloned, remote not reachable (auth/network?)")
        profiles = root / "context" / "codebases"
        if not (profiles / f"{name}.md").is_file() and not any(profiles.glob(f"{name}--*.md")):
            add("WARN", f"profile {name}", "missing; re-run /ai-workspace:init")
    single = any(spec.partition("=")[2] == "." for spec in codebases)
    for f in ((".claude/settings.local.json",) if single else (".claude/settings.json", "CLAUDE.md")):
        if not (root / f).is_file():
            add("WARN", f, "missing; re-run /ai-workspace:init and approve writes under .claude/")


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".")
    p.add_argument("--tracker")
    p.add_argument("--host", choices=["github", "gitlab"])
    p.add_argument("--codebases", default="")
    a = p.parse_args(argv)
    check_tools(a.host)
    check_tracker(a.tracker)
    check_workspace(Path(a.root).resolve(), [c for c in a.codebases.split(",") if c])
    width = max(len(c) for _, c, _ in results)
    for status, check, detail in results:
        print(f"{status:<5} {check:<{width}}  {detail}")
    return 1 if any(s == "FAIL" for s, _, _ in results) else 0


if __name__ == "__main__":
    sys.exit(main())
