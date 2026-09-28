#!/usr/bin/env python3
"""Workspace knowledge base: index, search and freshness of the documents under context/.

  kb.py index    [--root WS]                     build/refresh the search index (context/.kb.sqlite)
  kb.py search   [--root WS] "query" [--limit 5] [--kind feature,decision]   -> JSON results
  kb.py index-md [--root WS]                     rewrite context/INDEX.md from the documents' frontmatter
  kb.py stale    [--root WS] [--ref CODEBASE=REF ...]   -> JSON: documents whose sources changed since written
                                                 (compares against HEAD, or the given ref, e.g. origin/main)
  kb.py check    [--root WS]                     -> warnings: missing frontmatter, documents over size limits

Documents are markdown files under context/ with a small frontmatter block:

  ---
  title: Payslip generation
  kind: feature                  # overview | architecture | feature | codebase | decision | learning | brief
  summary: One line shown in INDEX.md and search results.
  tags: [payroll, tax]
  codebases: [backend, frontend]
  sources: ["backend:src/payslip/", "frontend:src/pages/payslip/"]
  generated_from: { backend: 3f2a1c9, frontend: 88b0e41 }
  updated: 2026-09-28
  ---

The markdown files are the source of truth (reviewable, committed with the workspace); the index is a
disposable cache. Search uses SQLite FTS5 (BM25, title and headings weighted) and falls back to a
pure-Python scorer when FTS5 is unavailable. Only the Python standard library is used.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

KINDS = ("brief", "overview", "architecture", "feature", "codebase", "decision", "learning")
KIND_BY_FOLDER = {"product": "overview", "features": "feature", "architecture": "architecture",
                  "codebases": "codebase", "decisions": "decision", "learnings": "learning"}
LINE_BUDGET = {"overview": 150, "architecture": 200, "feature": 150, "codebase": 100,
               "decision": 60, "learning": 60, "brief": 80}
SKIP = {"INDEX.md"}
TOKEN = re.compile(r"[A-Za-z0-9_]+")
STOP = set("a an and are as at be by for from how in is it of on or that the this to was what when where "
           "which who why with does do can should into our your".split())


# --- documents ------------------------------------------------------------------------------

def parse_value(v: str):
    v = v.strip()
    if v.startswith("[") and v.endswith("]"):
        return [x.strip().strip("\"'") for x in v[1:-1].split(",") if x.strip()]
    if v.startswith("{") and v.endswith("}"):
        out = {}
        for pair in v[1:-1].split(","):
            if ":" in pair:
                k, val = pair.split(":", 1)
                out[k.strip().strip("\"'")] = val.strip().strip("\"'")
        return out
    return v.strip("\"'")


def read_doc(path: Path, root: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    meta, body = {}, text
    m = re.match(r"\A---\n(.*?)\n---\n?", text, re.S)
    if m:
        body = text[m.end():]
        for line in m.group(1).splitlines():
            if re.match(r"^[A-Za-z_][\w-]*\s*:", line):
                k, v = line.split(":", 1)
                meta[k.strip()] = parse_value(v.split(" #", 1)[0])
    rel = path.relative_to(root).as_posix()
    folder = path.parent.name
    kind = meta.get("kind") or ("brief" if path.name == "brief.md" else KIND_BY_FOLDER.get(folder, "note"))
    title = meta.get("title") or next((ln[2:].strip() for ln in body.splitlines() if ln.startswith("# ")), path.stem)
    return {"path": rel, "kind": kind, "title": title, "summary": meta.get("summary", ""),
            "tags": meta.get("tags") if isinstance(meta.get("tags"), list) else [],
            "codebases": meta.get("codebases") if isinstance(meta.get("codebases"), list) else
                         ([meta["codebase"]] if isinstance(meta.get("codebase"), str) else []),
            "sources": meta.get("sources") if isinstance(meta.get("sources"), list) else [],
            "generated_from": meta.get("generated_from") if isinstance(meta.get("generated_from"), dict) else {},
            "has_frontmatter": bool(m), "body": body, "lines": len(text.splitlines()),
            "hash": hashlib.sha1(text.encode()).hexdigest()}


def documents(root: Path) -> list[dict]:
    ctx = root / "context"
    if not ctx.is_dir():
        return []
    return [read_doc(p, root) for p in sorted(ctx.rglob("*.md")) if p.name not in SKIP]


def sections(doc: dict) -> list[tuple[str, str]]:
    """(heading, text) chunks, so search returns the relevant part of a long document."""
    out, heading, buf = [], doc["title"], []
    for line in doc["body"].splitlines():
        if re.match(r"^#{1,3} ", line):
            if "".join(buf).strip():
                out.append((heading, "\n".join(buf).strip()))
            heading, buf = line.lstrip("#").strip(), []
        else:
            buf.append(line)
    if "".join(buf).strip():
        out.append((heading, "\n".join(buf).strip()))
    return out or [(doc["title"], doc["summary"])]


# --- index ----------------------------------------------------------------------------------

def db_path(root: Path) -> Path:
    return root / "context" / ".kb.sqlite"


def connect(root: Path, fts: bool):
    con = sqlite3.connect(db_path(root))
    con.execute("CREATE TABLE IF NOT EXISTS docs (path TEXT PRIMARY KEY, hash TEXT, kind TEXT, title TEXT, "
                "summary TEXT, tags TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
    if fts:
        con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(path UNINDEXED, kind UNINDEXED, "
                    "title, heading, body, tags, tokenize='porter unicode61')")
    else:
        con.execute("CREATE TABLE IF NOT EXISTS chunks (path TEXT, kind TEXT, title TEXT, heading TEXT, "
                    "body TEXT, tags TEXT)")
    return con


def fts_available() -> bool:
    if os.environ.get("KB_NO_FTS"):
        return False
    try:
        sqlite3.connect(":memory:").execute("CREATE VIRTUAL TABLE t USING fts5(x)")
        return True
    except sqlite3.OperationalError:
        return False


def build_index(root: Path) -> dict:
    fts = fts_available()
    (root / "context").mkdir(exist_ok=True)
    con = connect(root, fts)
    stored = dict(con.execute("SELECT path, hash FROM docs"))
    mode = dict(con.execute("SELECT key, value FROM meta")).get("mode")
    if mode and mode != ("fts" if fts else "plain"):   # engine changed: rebuild from scratch
        con.close()
        db_path(root).unlink()
        con, stored = connect(root, fts), {}
    docs = documents(root)
    seen, changed = set(), 0
    for d in docs:
        seen.add(d["path"])
        if stored.get(d["path"]) == d["hash"]:
            continue
        changed += 1
        con.execute("DELETE FROM chunks WHERE path = ?", (d["path"],))
        con.execute("INSERT OR REPLACE INTO docs VALUES (?,?,?,?,?,?)",
                    (d["path"], d["hash"], d["kind"], d["title"], d["summary"], " ".join(d["tags"])))
        for heading, text in sections(d):
            con.execute("INSERT INTO chunks VALUES (?,?,?,?,?,?)",
                        (d["path"], d["kind"], d["title"], heading, text, " ".join(d["tags"] + d["codebases"])))
    removed = [p for p in stored if p not in seen]
    for p in removed:
        con.execute("DELETE FROM chunks WHERE path = ?", (p,))
        con.execute("DELETE FROM docs WHERE path = ?", (p,))
    con.execute("INSERT OR REPLACE INTO meta VALUES ('mode', ?)", ("fts" if fts else "plain",))
    con.commit()
    con.close()
    return {"documents": len(docs), "updated": changed, "removed": len(removed), "engine": "fts5" if fts else "plain"}


def terms(query: str) -> list[str]:
    return [t.lower() for t in TOKEN.findall(query) if t.lower() not in STOP and len(t) > 1]


def snippet(text: str, words: list[str], width: int = 240) -> str:
    low = text.lower()
    pos = min((low.find(w) for w in words if low.find(w) >= 0), default=0)
    start = max(0, pos - width // 3)
    s = re.sub(r"\s+", " ", text[start:start + width]).strip()
    return ("…" if start else "") + s + ("…" if start + width < len(text) else "")


def search(root: Path, query: str, limit: int, kinds: set[str]) -> list[dict]:
    build_index(root)  # cheap when nothing changed; keeps results current
    words = terms(query)
    if not words:
        return []
    con = sqlite3.connect(db_path(root))
    mode = dict(con.execute("SELECT key, value FROM meta")).get("mode")
    rows = []
    if mode == "fts":
        match = " OR ".join(f'"{w}"*' for w in words)
        rows = con.execute("SELECT path, kind, title, heading, body, bm25(chunks, 0, 0, 5.0, 3.0, 1.0, 2.0) "
                           "FROM chunks WHERE chunks MATCH ? ORDER BY 6 LIMIT ?", (match, limit * 4)).fetchall()
        results = [(p, k, t, h, b, -score) for p, k, t, h, b, score in rows]
    else:
        all_rows = con.execute("SELECT path, kind, title, heading, body, tags FROM chunks").fetchall()
        n = max(len(all_rows), 1)
        df = {w: sum(1 for r in all_rows if w in " ".join(r[2:]).lower()) for w in words}
        results = []
        for p, k, t, h, b, tags in all_rows:
            score = 0.0
            for w in words:
                idf = math.log(1 + n / (1 + df[w]))
                score += idf * (5 * t.lower().count(w) + 3 * h.lower().count(w) + 2 * tags.lower().count(w)
                                + min(b.lower().count(w), 5))
            if score > 0:
                results.append((p, k, t, h, b, score))
        results.sort(key=lambda r: -r[5])
    con.close()
    out, seen = [], set()
    for p, k, t, h, b, score in results:
        if kinds and k not in kinds:
            continue
        key = (p, h)
        if key in seen:
            continue
        seen.add(key)
        out.append({"path": p,
                    "kind": k, "title": t, "section": h, "snippet": snippet(b, words),
                    "score": round(score, 3)})
        if len(out) >= limit:
            break
    return out


# --- INDEX.md, staleness, checks ------------------------------------------------------------

def write_index_md(root: Path) -> Path:
    docs = documents(root)
    order = ["brief", "overview", "architecture", "feature", "codebase", "decision", "learning", "note"]
    names = {"brief": "Product brief (written by you)", "overview": "Product", "architecture": "Architecture",
             "feature": "Features", "codebase": "Repositories", "decision": "Decisions", "learning": "Learnings",
             "note": "Other notes"}
    lines = ["<!-- generated by ai-workspace: kb.py index-md; edit the documents, not this file -->",
             "# Workspace knowledge", "",
             "Read the documents relevant to your task; search them with "
             "`python3 <plugin>/scripts/kb.py search \"<words>\"`. The code wins when a document disagrees.", ""]
    for kind in order:
        group = [d for d in docs if d["kind"] == kind]
        if not group:
            continue
        lines += [f"## {names[kind]}", ""]
        for d in sorted(group, key=lambda d: d["title"].lower()):
            summary = f": {d['summary']}" if d["summary"] else ""
            lines.append(f"- [{d['title']}]({Path(d['path']).relative_to('context').as_posix()}){summary}")
        lines.append("")
    out = root / "context" / "INDEX.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return out


def git(repo: Path, *args) -> tuple[int, str]:
    try:
        r = subprocess.run(["git", "-C", str(repo), *args], stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=30)
        return r.returncode, r.stdout
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def codebase_dir(root: Path, name: str) -> Path:
    if (root / "codebase" / name / ".git").exists():
        return root / "codebase" / name
    return root  # single mode: the workspace is the repository


def stale(root: Path, refs: dict | None = None) -> list[dict]:
    refs = refs or {}
    out = []
    for d in documents(root):
        if not d["generated_from"]:
            continue
        by_cb: dict[str, list[str]] = {}
        for src in d["sources"]:
            cb, _, path = src.partition(":")
            by_cb.setdefault(cb, []).append(path or ".")
        changes = []
        for cb, sha in d["generated_from"].items():
            repo = codebase_dir(root, cb)
            code, _ = git(repo, "cat-file", "-e", f"{sha}^{{commit}}")
            if code:
                changes.append({"codebase": cb, "reason": f"commit {sha} not found (history rewritten or not fetched)"})
                continue
            paths = by_cb.get(cb, ["."])
            code, files = git(repo, "diff", "--name-only", f"{sha}", refs.get(cb, "HEAD"), "--", *paths)
            files = [f for f in files.splitlines() if f]
            if files:
                changes.append({"codebase": cb, "since": sha, "changed_files": files[:20],
                                "more": max(0, len(files) - 20)})
        if changes:
            out.append({"path": d["path"], "title": d["title"], "changes": changes})
    return out


def check(root: Path) -> list[str]:
    warnings = []
    for d in documents(root):
        if not d["has_frontmatter"]:
            warnings.append(f"{d['path']}: no frontmatter (title, kind, summary)")
            continue
        if d["kind"] not in KINDS:
            warnings.append(f"{d['path']}: unknown kind '{d['kind']}'")
        if not d["summary"] and d["kind"] != "codebase":
            warnings.append(f"{d['path']}: no summary (shown in INDEX.md and search)")
        expected = {"feature": "context/product/features/", "decision": "context/decisions/",
                    "learning": "context/learnings/", "architecture": "context/architecture/"}.get(d["kind"])
        if expected and not d["path"].startswith(expected):
            warnings.append(f"{d['path']}: {d['kind']} documents belong in {expected}")
        budget = LINE_BUDGET.get(d["kind"])
        if budget and d["lines"] > budget:
            warnings.append(f"{d['path']}: {d['lines']} lines, over the {budget}-line budget for {d['kind']}; "
                            "split it or trim details that the code already shows")
    return warnings


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="ai-workspace knowledge base")
    p.add_argument("--root", default=".", help="workspace root (folder with workspace.yaml)")
    sub = p.add_subparsers(dest="op", required=True)
    sub.add_parser("index")
    s = sub.add_parser("search")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=5)
    s.add_argument("--kind", default="", help="comma-separated kinds to keep")
    sub.add_parser("index-md")
    st = sub.add_parser("stale")
    st.add_argument("--ref", action="append", default=[], metavar="CODEBASE=REF")
    sub.add_parser("check")
    a = p.parse_args(argv)
    root = Path(a.root).resolve()
    try:
        if a.op == "index":
            print(json.dumps(build_index(root)))
        elif a.op == "search":
            kinds = {k for k in a.kind.split(",") if k}
            print(json.dumps(search(root, a.query, a.limit, kinds), indent=2, ensure_ascii=False))
        elif a.op == "index-md":
            print(write_index_md(root).relative_to(root))
        elif a.op == "stale":
            refs = dict(r.split("=", 1) for r in a.ref if "=" in r)
            print(json.dumps(stale(root, refs), indent=2))
        else:
            warnings = check(root)
            print("\n".join(warnings) if warnings else "ok")
            return 1 if warnings else 0
    except sqlite3.Error as e:
        print(f"error: index problem ({e}); delete context/.kb.sqlite and run `kb.py index`", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
