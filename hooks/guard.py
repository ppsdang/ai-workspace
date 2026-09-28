#!/usr/bin/env python3
"""PreToolUse guard for Bash commands in an ai-workspace.

Decisions (returned as hook JSON on stdout, exit code 0):
  deny  - force-push, history-destroying or merge commands, pushes to protected branches
  ask   - outward-facing actions (push, MR/PR create/update, tracker comment/transition) so a
          human confirms each one in the permission prompt; also anything the guard cannot
          analyse reliably (sh -c, eval, command substitution, git aliases) that mentions push
  none  - everything else (normal permission flow applies)

This guards against honest mistakes and prompt-injected shortcuts. It is not a sandbox: a
determined process with shell access can always find another way. See SECURITY.md.

Configuration (workspace.yaml, optional):
  protected_branches: [main, master, "release/*"]    # inline or block list
  guard:
    confirm_outward: true      # set false to skip the confirmation prompts ("ask")
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

DEFAULT_PROTECTED = ["main", "master", "develop", "release/*"]
CONTROL = {";", "&&", "||", "|", "&", "|&", ";;", "(", ")", "{", "}", "\n"}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish"}
WRAPPERS = {"env", "command", "builtin", "exec", "nohup", "time", "sudo", "doas", "xargs", "nice", "timeout"}
GIT_BUILTINS = {
    "add", "am", "apply", "archive", "bisect", "blame", "branch", "bundle", "cat-file", "check-ignore",
    "checkout", "cherry", "cherry-pick", "clean", "clone", "commit", "config", "count-objects", "describe",
    "diff", "difftool", "fetch", "for-each-ref", "format-patch", "fsck", "gc", "grep", "help", "init",
    "log", "ls-files", "ls-remote", "ls-tree", "merge", "merge-base", "mergetool", "mv", "notes", "pull",
    "push", "range-diff", "rebase", "reflog", "remote", "reset", "restore", "rev-list", "rev-parse",
    "revert", "rm", "shortlog", "show", "show-ref", "sparse-checkout", "stash", "status", "submodule",
    "switch", "symbolic-ref", "tag", "update-index", "update-ref", "var", "version", "whatchanged",
    "worktree",
}
# git global options that consume the next argument
GIT_GLOBAL_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}
# git push options that consume the next argument (when not written as --opt=value)
PUSH_WITH_VALUE = {"-o", "--push-option", "--repo", "--receive-pack", "--exec"}
PUSH_DENY_LONG = {"--force", "--mirror", "--delete", "--prune", "--all", "--branches", "--force-if-includes"}
PUSH_DENY_SHORT = {"f", "d"}


class Decision(Exception):
    def __init__(self, kind: str, reason: str):
        super().__init__(reason)
        self.kind, self.reason = kind, reason


def emit(kind: str, reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": kind,
        "permissionDecisionReason": f"ai-workspace guard: {reason}",
    }}))


# --- workspace config -----------------------------------------------------------------------

def find_workspace(start: Path) -> Path | None:
    for d in (start, *start.parents):
        if (d / "workspace.yaml").is_file():
            return d
    return None


def read_config(ws: Path | None):
    """Return (protected_patterns, confirm_outward). Minimal YAML reading for two keys."""
    protected, confirm = list(DEFAULT_PROTECTED), True
    if not ws:
        return protected, confirm
    try:
        lines = (ws / "workspace.yaml").read_text(encoding="utf-8").splitlines()
    except OSError:
        return protected, confirm
    for i, line in enumerate(lines):
        if re.match(r"^protected_branches\s*:", line):
            rest = line.split(":", 1)[1].split("#", 1)[0].strip()
            items: list[str] = []
            if rest.startswith("["):
                items = [x.strip().strip("\"'") for x in rest.strip("[]").split(",")]
            elif not rest:
                for nxt in lines[i + 1:]:
                    m = re.match(r"^\s+-\s*(.+?)\s*(#.*)?$", nxt)
                    if m:
                        items.append(m.group(1).strip("\"'"))
                    elif nxt.strip() and not nxt.lstrip().startswith("#"):
                        break
            items = [x for x in items if x]
            if not items:
                raise Decision("ask", "workspace.yaml has protected_branches but it could not be parsed; "
                                      "confirm this command manually and fix the list")
            protected = items
        if re.match(r"^\s+confirm_outward\s*:\s*false\b", line, re.I):
            confirm = False
    return protected, confirm


def is_protected(branch: str, patterns: list[str]) -> bool:
    b = branch.casefold()
    return any(fnmatch.fnmatchcase(b, p.casefold()) for p in patterns)


# --- command parsing ------------------------------------------------------------------------

HEREDOC_RE = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def strip_heredocs(cmd: str) -> str:
    """Remove heredoc bodies: they are data (e.g. comment text), not commands."""
    lines, out, i = cmd.split("\n"), [], 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        delims = [m.group(2) for m in HEREDOC_RE.finditer(line)]
        i += 1
        for delim in delims:
            while i < len(lines) and lines[i].strip() != delim:
                i += 1
            i += 1  # skip the delimiter line
    return "\n".join(out)


def tokenize(cmd: str) -> list[str]:
    lex = shlex.shlex(cmd.replace("\n", " ; "), posix=True, punctuation_chars=";&|()")
    lex.whitespace_split = True
    lex.commenters = ""
    return list(lex)


def segments(tokens: list[str]):
    seg: list[str] = []
    for t in tokens:
        if t in CONTROL or set(t) <= set(";&|()"):
            if seg:
                yield seg
            seg = []
        else:
            seg.append(t)
    if seg:
        yield seg


def strip_prefix(words: list[str]) -> list[str]:
    """Drop env assignments and wrapper commands in front of the real command."""
    i = 0
    while i < len(words):
        w = words[i]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", w):
            i += 1
        elif os.path.basename(w) in WRAPPERS:
            i += 1
            while i < len(words) and words[i].startswith("-"):
                i += 1
            if os.path.basename(words[i - 1] if i else "") == "timeout" and i < len(words):
                i += 1  # timeout's duration argument
        else:
            break
    return words[i:]


def git_out(args: list[str], cwd: Path) -> str:
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def check_push(args: list[str], repo: Path, protected: list[str]) -> None:
    positional: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            positional += args[i + 1:]
            break
        if a.startswith("--"):
            name = a.split("=", 1)[0]
            if name in PUSH_DENY_LONG or name.startswith("--force-with-lease"):
                raise Decision("deny", f"'{name}' is not allowed; ask the user to run it themselves if intended")
            if name in PUSH_WITH_VALUE and "=" not in a:
                i += 1
        elif a.startswith("-") and len(a) > 1:
            flags = a[1:]
            for j, ch in enumerate(flags):
                if ch in PUSH_DENY_SHORT:
                    raise Decision("deny", f"'-{ch}' (force/delete) is not allowed")
                if f"-{ch}" in PUSH_WITH_VALUE:
                    if j == len(flags) - 1:
                        i += 1
                    break
        else:
            positional.append(a)
        i += 1

    refspecs = positional[1:]
    if not refspecs:
        target = git_out(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{push}"], repo)
        target = target.split("/", 1)[1] if "/" in target else target
        target = target or git_out(["rev-parse", "--abbrev-ref", "HEAD"], repo)
        if target and is_protected(target, protected):
            raise Decision("deny", f"this push would update protected branch '{target}'; "
                                   "push a feature branch and open an MR/PR")
        return
    current = git_out(["rev-parse", "--abbrev-ref", "HEAD"], repo)
    for ref in refspecs:
        if ref.startswith("+"):
            raise Decision("deny", f"force refspec '{ref}' is not allowed")
        if ref.startswith(":"):
            raise Decision("deny", f"deleting remote ref '{ref}' is not allowed")
        target = ref.split(":", 1)[1] if ":" in ref else ref
        if target == "HEAD":
            target = current
        target = re.sub(r"^refs/heads/", "", target)
        if target and is_protected(target, protected):
            raise Decision("deny", f"pushing to protected branch '{target}' is not allowed; "
                                   "push a feature branch and open an MR/PR")


OUTWARD = [
    (re.compile(r"^(gh)$"), [("pr", {"create", "edit", "comment", "close", "reopen", "review", "ready"}),
                             ("issue", {"comment", "edit", "close", "reopen", "create"}),
                             ("run", {"rerun", "cancel"})]),
    (re.compile(r"^(glab)$"), [("mr", {"create", "update", "note", "close", "reopen", "approve"}),
                               ("issue", {"note", "update", "close", "reopen", "create"}),
                               ("ci", {"retry", "run", "cancel", "delete"})]),
]
MERGE = {("gh", "pr", "merge"), ("glab", "mr", "merge")}


def analyse(cmd: str, cwd: Path, protected: list[str], confirm: bool) -> None:
    cmd = strip_heredocs(cmd)
    has_push = re.search(r"\bpush\b", cmd) is not None
    if has_push and ("$(" in cmd or "`" in cmd or re.search(r"\beval\b", cmd)):
        raise Decision("ask", "command substitution or eval around a push cannot be checked; confirm it manually")

    try:
        tokens = tokenize(cmd)
    except ValueError:
        if has_push or "gh " in cmd or "glab " in cmd:
            raise Decision("ask", "could not parse this command; confirm it manually")
        return

    base = cwd
    outward: list[str] = []
    for seg in segments(tokens):
        words = strip_prefix(seg)
        if not words:
            continue
        prog = os.path.basename(words[0])

        if prog in ("cd", "pushd") and len(words) > 1:
            base = (base / os.path.expanduser(words[1])).resolve()
            continue
        if prog in SHELLS and "-c" in words[1:]:
            inner = words[words.index("-c") + 1] if words.index("-c") + 1 < len(words) else ""
            analyse(inner, base, protected, confirm)  # recurse into sh -c "..."
            continue
        if words[0].startswith("$"):
            if has_push:
                raise Decision("ask", "a variable is used as the command; confirm it manually")
            continue

        if prog == "git":
            repo, i, sub = base, 1, ""
            while i < len(words):
                w = words[i]
                if w in GIT_GLOBAL_WITH_VALUE:
                    val = words[i + 1] if i + 1 < len(words) else ""
                    if w == "-C":
                        repo = (repo / val).resolve()
                    if w == "-c" and val.lower().startswith("alias."):
                        raise Decision("ask", "inline git alias definitions cannot be checked; confirm manually")
                    i += 2
                elif w.startswith("--") and "=" in w:
                    i += 1
                elif w.startswith("-"):
                    i += 1
                else:
                    sub = w
                    i += 1
                    break
            args = words[i:]
            if sub == "push":
                check_push(args, repo, protected)
                outward.append("git push")
            elif sub == "config" and any(a.lower().startswith("alias.") for a in args) and has_push:
                raise Decision("ask", "defining a git alias that pushes cannot be checked; confirm manually")
            elif sub == "reset" and "--hard" in args:
                raise Decision("ask", "git reset --hard discards work; confirm it manually")
            elif sub == "clean" and any(re.match(r"^-[a-z]*f", a) for a in args):
                raise Decision("ask", "git clean -f deletes untracked files; confirm it manually")
            elif sub == "branch" and any(a in ("-D", "--delete", "-d") or re.match(r"^-[a-zA-Z]*D", a) for a in args):
                raise Decision("ask", "deleting a branch; confirm it manually")
            elif sub and sub not in GIT_BUILTINS:
                alias = git_out(["config", "--get", f"alias.{sub}"], repo)
                if re.search(r"\bpush\b", alias):
                    raise Decision("ask", f"git alias '{sub}' runs push; confirm it manually")
            continue

        for pattern, groups in OUTWARD:
            if pattern.match(prog) and len(words) > 2:
                if (prog, words[1], words[2]) in MERGE:
                    raise Decision("deny", "merging MRs/PRs is left to humans")
                for noun, verbs in groups:
                    if words[1] == noun and words[2] in verbs:
                        outward.append(f"{prog} {noun} {words[2]}")

        if prog in ("gh", "glab") and len(words) > 1 and words[1] == "api":
            api_args = words[2:]
            method = next((api_args[k + 1].upper() for k, a in enumerate(api_args[:-1])
                           if a in ("-X", "--method")), "")
            method = method or next((a.split("=", 1)[1].upper() for a in api_args
                                     if a.startswith(("--method=", "-X="))), "")
            has_fields = any(a in ("-f", "-F", "--field", "--raw-field", "--input") or
                             a.startswith(("--field=", "--raw-field=", "--input=")) for a in api_args)
            is_graphql = bool(api_args) and api_args[0] == "graphql"
            if is_graphql:
                if re.search(r"\bmutation\b", " ".join(api_args)):
                    outward.append(f"{prog} api graphql mutation")
            elif method in ("POST", "PUT", "PATCH", "DELETE") or (has_fields and method != "GET"):
                if method == "DELETE":
                    raise Decision("ask", f"{prog} api DELETE; confirm it manually")
                outward.append(f"{prog} api {method or 'POST'}")

        if prog.startswith("python") and any(w.endswith("review_threads.py") for w in words) and "reply" in words:
            outward.append("MR/PR review reply")
        if prog.startswith("python") and any(w.endswith("ci.py") for w in words) and "rerun" in words:
            outward.append("CI re-run")

        if prog.startswith("python") and any(w.endswith("tracker.py") for w in words):
            ops = [w for w in words if w in ("comment", "transition")]
            if ops and "markdown" not in words:
                outward.append(f"tracker {ops[0]}")

    if outward and confirm:
        raise Decision("ask", "outward-facing action (" + ", ".join(dict.fromkeys(outward)) +
                              "). Confirm it matches what was approved at the gate")


def main() -> int:
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
        cmd = (data.get("tool_input") or {}).get("command") or ""
        cwd = Path(data.get("cwd") or os.getcwd())
    except (json.JSONDecodeError, AttributeError):
        if re.search(r"\bpush\b|\bgh\b|\bglab\b", raw):
            emit("ask", "could not read the hook input; confirm this command manually")
        return 0
    if not cmd:
        return 0
    if not cwd.is_absolute():
        cwd = Path(os.getcwd()) / cwd
    try:
        protected, confirm = read_config(find_workspace(cwd.resolve()))
        analyse(cmd, cwd.resolve(), protected, confirm)
    except Decision as d:
        emit(d.kind, d.reason)
    except Exception as e:  # never crash into "allow" silently on push-like commands
        if re.search(r"\bpush\b", cmd):
            emit("ask", f"guard error ({type(e).__name__}); confirm this command manually")
    return 0


if __name__ == "__main__":
    sys.exit(main())
