#!/usr/bin/env python3
"""SessionStart hook: tell Claude which ai-workspace tasks are in progress.

Prints a few lines of plain text (added to the session context) when the session starts inside an
ai-workspace with unfinished tasks; prints nothing otherwise. Never fails the session.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

NEXT = {
    "awaiting-plan-approval": "waiting for plan approval",
    "awaiting-ship-approval": "waiting for ship approval",
    "blocked": "blocked",
    "shipped": "MRs open: /ai-workspace:ci or /ai-workspace:respond",
}
MAX_TASKS = 8


def frontmatter(text: str) -> dict:
    m = re.match(r"\A---\n(.*?)\n---", text, re.S)
    meta = {}
    for line in (m.group(1).splitlines() if m else []):
        if ":" in line and not line.startswith((" ", "\t")):
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta


def main() -> int:
    try:
        data = json.loads(sys.stdin.read() or "{}")
        cwd = Path(data.get("cwd") or ".").resolve()
    except (json.JSONDecodeError, OSError):
        return 0
    ws = next((d for d in (cwd, *cwd.parents) if (d / "workspace.yaml").is_file()), None)
    if not ws or not (ws / "tasks").is_dir():
        return 0
    active = []
    for state in (ws / "tasks").glob("*/state.md"):
        try:
            meta = frontmatter(state.read_text(encoding="utf-8"))
        except OSError:
            continue
        phase = meta.get("phase", "?")
        if phase in ("done", ""):
            continue
        active.append((state.stat().st_mtime, meta.get("key") or state.parent.name, phase,
                       meta.get("blocked_reason", "")))
    if not active:
        return 0
    active.sort(reverse=True)
    lines = [f"ai-workspace: {len(active)} unfinished task(s) in this workspace (newest first):"]
    for _, key, phase, reason in active[:MAX_TASKS]:
        note = NEXT.get(phase, "in progress: /ai-workspace:task " + key + " resumes it")
        if phase == "blocked" and reason:
            note += f" ({reason[:80]})"
        lines.append(f"- {key}: {phase}; {note}")
    if len(active) > MAX_TASKS:
        lines.append(f"- and {len(active) - MAX_TASKS} more in tasks/")
    lines.append("Mention these only if relevant to what the user asks.")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # a status hint must never break session start
        sys.exit(0)
