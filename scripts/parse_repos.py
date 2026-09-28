#!/usr/bin/env python3
"""Turn whatever the user pasted into a list of repositories.

  parse_repos.py [--existing name1,name2] < pasted.txt      -> JSON [{"name", "url"}]

Accepts links one per line, separated by spaces or commas, inside other text or markdown, with or
without a name in front ("backend git@..."). Understands ssh (git@host:group/repo.git), ssh://, https
and local folder paths (existing directories). Names come from the repository name in the link, unless
the user wrote a name in front of it; clashes get the parent group added (payroll-api, billing-api).
Exit code 2 when nothing that looks like a repository was found.
Only the Python standard library is used.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

SSH_SCP = r"[\w.-]+@[\w.-]+:[\w./~-]+"
URL = r"(?:https?|ssh|git)://[^\s,;<>()\"'`]+"
LOCAL = r"(?:~|\.{1,2})?/[^\s,;<>()\"'`]+"
WINDOWS = r"[A-Za-z]:[\\/][^\s,;<>()\"'`]+"          # C:\Users\me\code\api or C:/Users/...
LINK = re.compile(rf"(?P<link>{URL}|{WINDOWS}|{SSH_SCP}|{LOCAL})")
NAME_OK = re.compile(r"^[A-Za-z0-9._-]+$")


def split_link(link: str) -> tuple[str, str]:
    """(group, repo) of a link, e.g. ("payroll", "backend")."""
    u = link.rstrip("/\\").removesuffix(".git")
    if "://" in u:
        path = re.sub(r"^[a-z+]+://[^/]+", "", u)
    elif re.match(SSH_SCP + "$", u):
        path = u.split(":", 1)[1]
    else:
        path = u
    parts = [p for p in re.split(r"[\\/]", path) if p and p not in (".", "..", "~") and not re.fullmatch(r"[A-Za-z]:", p)]
    if not parts:
        return "", ""
    return (parts[-2] if len(parts) > 1 else ""), parts[-1]


def clean_name(text: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-.")
    return name.lower() or "repo"


def is_repo_link(link: str) -> bool:
    if re.match(SSH_SCP + "$", link) or "://" in link:
        return True
    path = os.path.expanduser(link)
    return os.path.isdir(path)  # local paths only when the folder exists


def parse(text: str, existing: set[str]) -> list[dict]:
    found, seen_urls = [], set()
    for line in text.replace(",", "\n").replace(";", "\n").splitlines():
        line = re.sub(r"[`*\[\]]", " ", line)                   # markdown decoration
        for m in LINK.finditer(line):
            link = m.group("link").rstrip(".:)")
            if not is_repo_link(link) or link in seen_urls:
                continue
            # A name counts only when it is the only word between the previous link (or the line start)
            # and this link, as in "backend git@...". Prose such as "and also git@..." never becomes a name.
            prev_end = max((p.end() for p in LINK.finditer(line) if p.end() <= m.start()), default=0)
            words = [w for w in line[prev_end:m.start()].split() if not re.fullmatch(r"[-*+]|\d+[.)]", w)]
            explicit = words[0] if len(words) == 1 and NAME_OK.match(words[0]) and words[0].lower() not in (
                "and", "also", "or", "plus", "then", "repo", "repos", "repository", "here") else None
            group, repo = split_link(link)
            if not repo:
                continue
            seen_urls.add(link)
            found.append({"name": clean_name(explicit) if explicit else clean_name(repo),
                          "url": link, "_group": clean_name(group) if group else "", "_explicit": bool(explicit)})
    # resolve clashes (with each other and with codebases already in workspace.yaml)
    taken = set(existing)
    counts: dict[str, int] = {}
    for r in found:
        counts[r["name"]] = counts.get(r["name"], 0) + 1
    for r in found:
        name = r["name"]
        if (counts[name] > 1 or name in existing) and not r["_explicit"] and r["_group"]:
            name = f"{r['_group']}-{name}"
        base, n = name, 2
        while name in taken:
            name = f"{base}-{n}"
            n += 1
        taken.add(name)
        r["name"] = name
    return [{"name": r["name"], "url": r["url"]} for r in found]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--existing", default="", help="codebase names already in workspace.yaml")
    a = p.parse_args(argv)
    repos = parse(sys.stdin.read(), {n for n in a.existing.split(",") if n})
    print(json.dumps(repos, indent=2))
    return 0 if repos else 2


if __name__ == "__main__":
    sys.exit(main())
