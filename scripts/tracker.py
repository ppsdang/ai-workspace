#!/usr/bin/env python3
"""Task tracker adapters for ai-workspace.

Every adapter maps a tracker onto three operations and one normalised ticket shape, so the
/task flow never depends on which tracker a workspace uses.

  tracker.py --type TYPE [options] fetch KEY          -> prints normalised ticket JSON
  tracker.py --type TYPE [options] comment KEY        -> comment text read from stdin
  tracker.py --type TYPE [options] transition KEY STATUS

Types and their options (secrets always come from environment variables, never arguments):
  jira      --base-url URL              env JIRA_API_TOKEN, optional JIRA_EMAIL (Cloud basic auth;
                                        without it the token is sent as a Bearer PAT for Server/DC)
            [--project KEY] [--acceptance-field customfield_NNNNN]
  github    --repo OWNER/REPO           uses the `gh` CLI and its login; a key like owner/repo#42
            [--status-labels a,b]       overrides --repo; status labels removed on transition
  trello    (none)                      env TRELLO_API_KEY, TRELLO_TOKEN
  markdown  --path DIR                  task files, e.g. backlog/task1.md, relative to --root
  custom    --fetch-cmd / --comment-cmd / --transition-cmd   command templates with {key} / {status};
                                        comment text is passed on stdin

Common: --max-comments N (default 20, newest kept). Errors go to stderr as one line, exit code 1.
Only the Python standard library is used.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import re
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

KEY_RE = re.compile(r"^[A-Za-z0-9._#/:-]+$")


class TrackerError(Exception):
    pass


def ticket(key, title, *, description="", status="", type_="", priority="", url="",
           acceptance=None, labels=None, comments=None, source=""):
    return {
        "key": key,
        "title": title,
        "type": type_,
        "status": status,
        "priority": priority,
        "url": url,
        "description": description or "",
        "acceptance_criteria": acceptance or [],
        "labels": labels or [],
        "comments": comments or [],
        "source": source,
    }


def acceptance_from_text(text: str) -> list[str]:
    """Pull bullet items under an 'Acceptance criteria' heading, if present."""
    lines = (text or "").splitlines()
    out, inside = [], False
    for line in lines:
        stripped = line.strip()
        if re.match(r"^(#+\s*|h\d\.\s*|\*)?acceptance criteria\b", stripped, re.I):
            inside = True
            continue
        if inside:
            if re.match(r"^(#+\s|h\d\.\s)", stripped):
                break
            m = re.match(r"^(?:[-*+]|\d+[.)]|\[[ xX]\])\s+(.*)", stripped)
            if m:
                out.append(re.sub(r"^\[[ xX]\]\s*", "", m.group(1)))
    return out


def flatten_text(value) -> str:
    """Plain text from a string, a list, or an Atlassian Document Format node."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(flatten_text(v) for v in value)
    if isinstance(value, dict):
        if value.get("type") == "text":
            return value.get("text", "")
        inner = "".join(flatten_text(c) for c in value.get("content") or [])
        if value.get("type") == "listItem":
            return f"- {inner.strip()}\n"
        if value.get("type") in ("paragraph", "heading"):
            return inner + "\n"
        return inner or str(value.get("value", ""))
    return str(value)


def acceptance_from_value(value) -> list[str]:
    """Acceptance criteria from a dedicated field: one item per bullet or non-empty line."""
    text = flatten_text(value)
    items = []
    for line in text.splitlines():
        line = re.sub(r"^\s*(?:[-*+#]|\d+[.)]|\[[ xX]\])\s*", "", line).strip()
        if line:
            items.append(line)
    return items


def http(method, url, *, headers=None, body=None):
    data = None
    headers = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    headers.setdefault("Accept", "application/json")
    path = urllib.parse.urlsplit(url).path
    for attempt in range(4):
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
            break
        except urllib.error.HTTPError as e:
            if e.code in (429, 502, 503) and attempt < 3:
                retry_after = e.headers.get("Retry-After", "")
                time.sleep(min(float(retry_after) if retry_after.isdigit() else 2 ** attempt, 10))
                continue
            detail = e.read().decode(errors="replace")[:300]
            hint = ""
            if e.code in (401, 403):
                hint = " (check the token and its permissions"
                hint += "; for Jira Cloud also set JIRA_EMAIL)" if "/rest/api/" in path else ")"
            raise TrackerError(f"{method} {path} -> HTTP {e.code}{hint}: {detail}") from None
        except urllib.error.URLError as e:
            raise TrackerError(f"cannot reach {urllib.parse.urlsplit(url).netloc}: {e.reason}") from None
        except TimeoutError:
            raise TrackerError(f"{method} {path} timed out after 30s") from None
    if not raw.strip():
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise TrackerError(f"{method} {path} returned non-JSON (often a login page): check the base URL "
                           "and credentials") from None


def need_env(*names):
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        raise TrackerError(f"missing environment variable(s): {', '.join(missing)}")
    return [os.environ[n] for n in names]


# --- jira -----------------------------------------------------------------------------------

class Jira:
    def __init__(self, args):
        if not args.base_url:
            raise TrackerError("jira needs --base-url")
        self.base = args.base_url.rstrip("/")
        self.acceptance_field = args.acceptance_field
        self.project = args.project
        (token,) = need_env("JIRA_API_TOKEN")
        email = os.environ.get("JIRA_EMAIL")
        if email:
            auth = base64.b64encode(f"{email}:{token}".encode()).decode()
            self.headers = {"Authorization": f"Basic {auth}"}
        else:
            self.headers = {"Authorization": f"Bearer {token}"}

    def _api(self, method, path, body=None):
        # API v2 takes and returns plain text bodies and works on Cloud and Server/DC.
        return http(method, f"{self.base}/rest/api/2{path}", headers=self.headers, body=body)

    def fetch(self, key):
        if self.project and not key.upper().startswith(f"{self.project.upper()}-"):
            print(f"warning: {key} is not in project {self.project}", file=sys.stderr)
        fields = "summary,description,status,issuetype,priority,labels,comment"
        if self.acceptance_field:
            fields += f",{self.acceptance_field}"
        d = self._api("GET", f"/issue/{urllib.parse.quote(key)}?fields={fields}")
        f = d.get("fields", {})
        desc = f.get("description") or ""
        acceptance = acceptance_from_text(desc)
        if self.acceptance_field and f.get(self.acceptance_field):
            acceptance = acceptance_from_value(f[self.acceptance_field]) or acceptance
        comments = [
            {"author": (c.get("author") or {}).get("displayName", ""), "created": c.get("created", ""),
             "body": c.get("body", "")}
            for c in ((f.get("comment") or {}).get("comments") or [])
        ]
        return ticket(
            d.get("key", key), f.get("summary", ""), description=desc,
            status=(f.get("status") or {}).get("name", ""),
            type_=(f.get("issuetype") or {}).get("name", ""),
            priority=(f.get("priority") or {}).get("name", ""),
            url=f"{self.base}/browse/{d.get('key', key)}",
            acceptance=acceptance, labels=f.get("labels") or [],
            comments=comments, source="jira",
        )

    def comment(self, key, text):
        self._api("POST", f"/issue/{urllib.parse.quote(key)}/comment", {"body": text})

    def transition(self, key, status):
        options = self._api("GET", f"/issue/{urllib.parse.quote(key)}/transitions").get("transitions", [])
        match = next((t for t in options if status.lower() in
                      (t.get("name", "").lower(), (t.get("to") or {}).get("name", "").lower())), None)
        if not match:
            names = ", ".join(t.get("name", "") for t in options) or "none"
            raise TrackerError(f"no transition to '{status}' from the current status; available: {names}")
        self._api("POST", f"/issue/{urllib.parse.quote(key)}/transitions", {"transition": {"id": match["id"]}})


# --- github ---------------------------------------------------------------------------------

class GitHub:
    def __init__(self, args):
        m = re.match(r"^([\w.-]+/[\w.-]+)#\d+$", args.key or "")
        self.repo = m.group(1) if m else args.repo
        if not self.repo:
            raise TrackerError("github needs --repo OWNER/REPO (or a key like owner/repo#42)")
        self.status_labels = [x.strip() for x in (args.status_labels or "").split(",") if x.strip()]

    @staticmethod
    def _num(key):
        m = re.search(r"(\d+)$", key)
        if not m:
            raise TrackerError(f"github issue key must end in a number, got '{key}'")
        return m.group(1)

    def _gh(self, *argv, stdin=None):
        try:
            res = subprocess.run(["gh", *argv, "--repo", self.repo], input=stdin,
                                 stdin=None if stdin is not None else subprocess.DEVNULL,
                                 capture_output=True, text=True, timeout=60)
        except FileNotFoundError:
            raise TrackerError("the `gh` CLI is not installed") from None
        except subprocess.TimeoutExpired:
            raise TrackerError("gh timed out after 60s") from None
        if res.returncode:
            raise TrackerError(res.stderr.strip() or f"gh exited {res.returncode}")
        return res.stdout

    def fetch(self, key):
        n = self._num(key)
        d = json.loads(self._gh("issue", "view", n, "--json",
                                "number,title,body,state,url,labels,comments"))
        body = d.get("body") or ""
        labels = [lb.get("name", "") for lb in d.get("labels") or []]
        comments = [{"author": (c.get("author") or {}).get("login", ""), "created": c.get("createdAt", ""),
                     "body": c.get("body", "")} for c in d.get("comments") or []]
        type_ = next((lb for lb in labels if lb.lower() in ("bug", "feature", "enhancement", "chore")), "")
        return ticket(f"#{d['number']}", d.get("title", ""), description=body, status=d.get("state", ""),
                      type_=type_, url=d.get("url", ""), acceptance=acceptance_from_text(body),
                      labels=labels, comments=comments, source="github")

    def comment(self, key, text):
        self._gh("issue", "comment", self._num(key), "--body-file", "-", stdin=text)

    def transition(self, key, status):
        n = self._num(key)
        s = status.lower()
        if s in ("closed", "close", "done"):
            self._gh("issue", "close", n)
        elif s in ("open", "reopen", "reopened"):
            self._gh("issue", "reopen", n)
        else:
            argv = ["issue", "edit", n, "--add-label", status]
            for old in self.status_labels:
                if old.lower() != s:
                    argv += ["--remove-label", old]
            self._gh(*argv)


# --- trello ---------------------------------------------------------------------------------

class Trello:
    def __init__(self, args):
        key, token = need_env("TRELLO_API_KEY", "TRELLO_TOKEN")
        self.base = os.environ.get("TRELLO_API_BASE", "https://api.trello.com").rstrip("/")
        self.headers = {"Authorization": f'OAuth oauth_consumer_key="{key}", oauth_token="{token}"'}

    @staticmethod
    def _card_id(key):
        m = re.search(r"trello\.com/c/([A-Za-z0-9]+)", key)
        return m.group(1) if m else key

    def _api(self, method, path, params=None, body=None):
        q = f"?{urllib.parse.urlencode(params)}" if params else ""
        return http(method, f"{self.base}/1{path}{q}", headers=self.headers, body=body)

    def fetch(self, key):
        cid = self._card_id(key)
        d = self._api("GET", f"/cards/{cid}", {
            "fields": "name,desc,url,shortLink,labels,idList",
            "checklists": "all", "actions": "commentCard", "actions_limit": "1000", "list": "true",
        })
        desc = d.get("desc") or ""
        acceptance = acceptance_from_text(desc)
        for cl in d.get("checklists") or []:
            acceptance += [i.get("name", "") for i in cl.get("checkItems") or []]
        comments = [{"author": (a.get("memberCreator") or {}).get("fullName", ""), "created": a.get("date", ""),
                     "body": (a.get("data") or {}).get("text", "")} for a in d.get("actions") or []]
        return ticket(d.get("shortLink") or cid, d.get("name", ""), description=desc,
                      status=(d.get("list") or {}).get("name", ""), url=d.get("url", ""),
                      acceptance=acceptance, labels=[lb.get("name", "") for lb in d.get("labels") or []],
                      comments=comments, source="trello")

    def comment(self, key, text):
        self._api("POST", f"/cards/{self._card_id(key)}/actions/comments", body={"text": text})

    def transition(self, key, status):
        cid = self._card_id(key)
        card = self._api("GET", f"/cards/{cid}", {"fields": "idBoard"})
        lists = self._api("GET", f"/boards/{card['idBoard']}/lists", {"fields": "name"})
        match = next((lst for lst in lists if lst.get("name", "").lower() == status.lower()), None)
        if not match:
            raise TrackerError(f"no list named '{status}'; lists: {', '.join(x.get('name', '') for x in lists)}")
        self._api("PUT", f"/cards/{cid}", {"idList": match["id"]})


# --- markdown -------------------------------------------------------------------------------

FM_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.S)


def split_frontmatter(text):
    m = FM_RE.match(text)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t", "#")):
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip("\"'")
    return meta, text[m.end():]


def set_frontmatter_field(text, field, value):
    m = FM_RE.match(text)
    if not m:
        return f"---\n{field}: {value}\n---\n\n{text}"
    block = m.group(1)
    if re.search(rf"^{re.escape(field)}:", block, re.M):
        block = re.sub(rf"^{re.escape(field)}:.*$", lambda _: f"{field}: {value}", block, count=1, flags=re.M)
    else:
        block = f"{block}\n{field}: {value}"
    return f"---\n{block}\n---\n{text[m.end():]}"


class Markdown:
    def __init__(self, args):
        if not args.path:
            raise TrackerError("markdown needs --path DIR")
        self.root = Path(args.root).resolve()
        self.dir = (self.root / args.path).resolve()
        if not self.dir.is_dir():
            raise TrackerError(f"task directory not found: {self.dir}")

    def _inside(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self.dir)
            return True
        except ValueError:
            return False

    def _find(self, key):
        direct = Path(key)
        candidates = [direct if direct.is_absolute() else Path.cwd() / direct, self.root / key,
                      self.dir / key, self.dir / f"{key}.md"]
        for c in candidates:
            if c.is_file() and c.suffix == ".md":
                if not self._inside(c):
                    raise TrackerError(f"task file must be inside {self.dir}: {key}")
                return c.resolve()
        for f in sorted(self.dir.rglob("*.md")):
            meta, _ = split_frontmatter(f.read_text(encoding="utf-8"))
            if meta.get("id", "").lower() == key.lower() or f.stem.lower() == key.lower():
                return f
        raise TrackerError(f"no task file for '{key}' in {self.dir}")

    def fetch(self, key):
        f = self._find(key)
        meta, body = split_frontmatter(f.read_text(encoding="utf-8"))
        title = meta.get("title", "")
        if not title:
            h = re.search(r"^#\s+(.+)$", body, re.M)
            title = h.group(1).strip() if h else f.stem
        return ticket(meta.get("id") or f.stem, title, description=body.strip(),
                      status=meta.get("status", ""), type_=meta.get("type", ""),
                      priority=meta.get("priority", ""), url=str(f), acceptance=acceptance_from_text(body),
                      labels=[x.strip() for x in meta.get("labels", "").strip("[]").split(",") if x.strip()],
                      source="markdown")

    def comment(self, key, text):
        f = self._find(key)
        content = f.read_text(encoding="utf-8").rstrip("\n")
        stamp = dt.date.today().isoformat()
        body = "\n".join(f"  {ln}" if ln.strip() else "" for ln in text.strip().splitlines())
        entry = f"- {stamp}: " + body.lstrip()
        if re.search(r"^## Activity\s*$", content, re.M):
            content += f"\n{entry}\n"
        else:
            content += f"\n\n## Activity\n\n{entry}\n"
        f.write_text(content, encoding="utf-8")

    def transition(self, key, status):
        f = self._find(key)
        f.write_text(set_frontmatter_field(f.read_text(encoding="utf-8"), "status", status), encoding="utf-8")


# --- custom ---------------------------------------------------------------------------------

class Custom:
    """Delegates to user-supplied commands, e.g. a script that calls an in-house tracker's API.

    Templates are split into argv first and placeholders substituted per argument, so a key or
    status can never inject shell syntax. fetch output may be normalised ticket JSON or plain text.
    """

    def __init__(self, args):
        self.cmds = {"fetch": args.fetch_cmd, "comment": args.comment_cmd, "transition": args.transition_cmd}
        self.root = args.root

    def _run(self, op, stdin=None, **values):
        tpl = self.cmds.get(op)
        if not tpl:
            raise TrackerError(f"custom tracker has no --{op}-cmd configured")
        argv = []
        for part in shlex.split(tpl):
            for name, value in values.items():
                part = part.replace("{" + name + "}", value)
            argv.append(part)
        try:
            res = subprocess.run(argv, input=stdin, stdin=None if stdin is not None else subprocess.DEVNULL,
                                 capture_output=True, text=True, timeout=120, cwd=self.root)
        except FileNotFoundError:
            raise TrackerError(f"command not found: {argv[0]}") from None
        except subprocess.TimeoutExpired:
            raise TrackerError(f"{argv[0]} timed out after 120s") from None
        if res.returncode:
            raise TrackerError(res.stderr.strip() or f"{argv[0]} exited {res.returncode}")
        return res.stdout

    def fetch(self, key):
        out = self._run("fetch", key=key).strip()
        try:
            d = json.loads(out)
            if not isinstance(d, dict):
                raise ValueError
        except ValueError:
            h = re.search(r"^#\s+(.+)$", out, re.M)
            return ticket(key, h.group(1).strip() if h else key, description=out,
                          acceptance=acceptance_from_text(out), source="custom")
        base = ticket(key, "", source="custom")
        base.update({k: v for k, v in d.items() if k in base})
        base["title"] = base["title"] or key
        if not base["acceptance_criteria"]:
            base["acceptance_criteria"] = acceptance_from_text(base["description"])
        return base

    def comment(self, key, text):
        self._run("comment", stdin=text, key=key)

    def transition(self, key, status):
        self._run("transition", key=key, status=status)


ADAPTERS = {"jira": Jira, "github": GitHub, "trello": Trello, "markdown": Markdown, "custom": Custom}


def main(argv=None):
    p = argparse.ArgumentParser(description="ai-workspace tracker adapter")
    p.add_argument("--type", required=True, choices=sorted(ADAPTERS))
    p.add_argument("--root", default=".", help="workspace root (markdown paths and custom cwd)")
    p.add_argument("--base-url")
    p.add_argument("--repo")
    p.add_argument("--path")
    p.add_argument("--fetch-cmd")
    p.add_argument("--comment-cmd")
    p.add_argument("--transition-cmd")
    p.add_argument("--project", help="jira: warn if the key is outside this project")
    p.add_argument("--acceptance-field", help="jira: custom field holding acceptance criteria, e.g. customfield_10042")
    p.add_argument("--status-labels", help="github: comma-separated status labels to remove on transition")
    p.add_argument("--max-comments", type=int, default=20, help="keep only the latest N comments (default 20)")
    sub = p.add_subparsers(dest="op", required=True)
    sub.add_parser("fetch").add_argument("key")
    sub.add_parser("comment").add_argument("key")
    t = sub.add_parser("transition")
    t.add_argument("key")
    t.add_argument("status")
    args = p.parse_args(argv)

    if not KEY_RE.match(args.key) and args.type != "markdown":
        print(f"error: invalid ticket key '{args.key}'", file=sys.stderr)
        return 65
    try:
        adapter = ADAPTERS[args.type](args)
        if args.op == "fetch":
            t = adapter.fetch(args.key)
            if args.max_comments >= 0 and len(t["comments"]) > args.max_comments:
                t["comments"] = t["comments"][-args.max_comments:] if args.max_comments else []
            print(json.dumps(t, indent=2, ensure_ascii=False))
        elif args.op == "comment":
            text = sys.stdin.read()
            if not text.strip():
                raise TrackerError("comment text is empty (pass it on stdin)")
            adapter.comment(args.key, text)
            print("ok")
        else:
            adapter.transition(args.key, args.status)
            print("ok")
    except TrackerError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # keep output readable for the agent; no raw tracebacks
        print(f"error: unexpected {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
