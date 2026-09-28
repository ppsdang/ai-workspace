#!/usr/bin/env python3
"""Fetch unresolved MR/PR review threads and post replies, for GitHub (gh) and GitLab (glab).

  review_threads.py list  <mr-or-pr-url>                  -> JSON list of unresolved threads
  review_threads.py reply <mr-or-pr-url> <thread-id>      -> reply text on stdin
  review_threads.py checks <mr-or-pr-url>                 -> JSON CI summary for the MR/PR head

Thread JSON: {id, path, line, author, body, url, comments: [{author, body}]}
Uses the host CLI's existing login. Only the Python standard library is used.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.parse

GH_PR = re.compile(r"^https?://(?P<host>[^/]+)/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<num>\d+)")
GL_MR = re.compile(r"^https?://(?P<host>[^/]+)/(?P<project>.+?)/-/merge_requests/(?P<iid>\d+)")

GH_THREADS_QUERY = """
query($owner: String!, $repo: String!, $num: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $num) {
      reviewThreads(first: 100) {
        nodes {
          id isResolved isOutdated path line
          comments(first: 50) { nodes { author { login } body url } }
        }
      }
    }
  }
}
"""


class Error(Exception):
    pass


def run(argv, stdin=None):
    try:
        r = subprocess.run(argv, input=stdin, stdin=None if stdin is not None else subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=90)
    except FileNotFoundError:
        raise Error(f"`{argv[0]}` is not installed") from None
    except subprocess.TimeoutExpired:
        raise Error(f"{argv[0]} timed out") from None
    if r.returncode:
        raise Error(r.stderr.strip() or f"{argv[0]} exited {r.returncode}")
    return r.stdout


def parse(url):
    if m := GH_PR.match(url):
        return "github", m.groupdict()
    if m := GL_MR.match(url):
        return "gitlab", m.groupdict()
    raise Error(f"not a GitHub PR or GitLab MR URL: {url}")


def gh(host, *args, stdin=None):
    argv = ["gh", "api", *args]
    if host != "github.com":
        argv += ["--hostname", host]
    return run(argv, stdin)


def glab(host, *args):
    return run(["glab", "api", *args, "--hostname", host])


# --- github ---------------------------------------------------------------------------------

def gh_list(p):
    out = gh(p["host"], "graphql", "-f", f"query={GH_THREADS_QUERY}", "-F", f"owner={p['owner']}",
             "-F", f"repo={p['repo']}", "-F", f"num={p['num']}")
    nodes = json.loads(out)["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]
    threads = []
    for t in nodes:
        if t.get("isResolved"):
            continue
        comments = [{"author": (c.get("author") or {}).get("login", ""), "body": c.get("body", "")}
                    for c in (t.get("comments") or {}).get("nodes") or []]
        first = ((t.get("comments") or {}).get("nodes") or [{}])[0]
        threads.append({"id": t["id"], "path": t.get("path"), "line": t.get("line"),
                        "outdated": bool(t.get("isOutdated")), "author": comments[0]["author"] if comments else "",
                        "body": comments[0]["body"] if comments else "", "url": first.get("url", ""),
                        "comments": comments})
    return threads


def gh_reply(p, thread_id, text):
    mutation = ("mutation($id: ID!, $body: String!) { addPullRequestReviewThreadReply("
                "input: {pullRequestReviewThreadId: $id, body: $body}) { comment { url } } }")
    out = gh(p["host"], "graphql", "-f", f"query={mutation}", "-f", f"id={thread_id}", "-F", "body=@-", stdin=text)
    return json.loads(out)["data"]["addPullRequestReviewThreadReply"]["comment"]["url"]


def gh_checks(p):
    pr = json.loads(gh(p["host"], f"repos/{p['owner']}/{p['repo']}/pulls/{p['num']}"))
    sha = pr["head"]["sha"]
    runs = json.loads(gh(p["host"], f"repos/{p['owner']}/{p['repo']}/commits/{sha}/check-runs?per_page=100"))
    checks = [{"name": c["name"], "status": c["status"], "conclusion": c.get("conclusion"),
               "url": c.get("html_url"), "id": c["id"]} for c in runs.get("check_runs", [])]
    return summarize(sha, checks, lambda c: c["status"] != "completed",
                     lambda c: c["conclusion"] in ("failure", "timed_out", "cancelled", "action_required"))


# --- gitlab ---------------------------------------------------------------------------------

def gl_base(p):
    return f"projects/{urllib.parse.quote(p['project'], safe='')}/merge_requests/{p['iid']}"


def gl_list(p):
    discussions = json.loads(glab(p["host"], f"{gl_base(p)}/discussions?per_page=100"))
    threads = []
    for d in discussions:
        notes = [n for n in d.get("notes") or [] if not n.get("system")]
        if not notes or not notes[0].get("resolvable") or all(n.get("resolved") for n in notes if n.get("resolvable")):
            continue
        first = notes[0]
        pos = first.get("position") or {}
        threads.append({"id": d["id"], "path": pos.get("new_path") or pos.get("old_path"),
                        "line": pos.get("new_line") or pos.get("old_line"), "outdated": False,
                        "author": (first.get("author") or {}).get("username", ""), "body": first.get("body", ""),
                        "url": "", "comments": [{"author": (n.get("author") or {}).get("username", ""),
                                                 "body": n.get("body", "")} for n in notes]})
    return threads


def gl_reply(p, thread_id, text):
    out = glab(p["host"], "--method", "POST", f"{gl_base(p)}/discussions/{thread_id}/notes", "-f", f"body={text}")
    return json.loads(out).get("id")


def gl_checks(p):
    mr = json.loads(glab(p["host"], gl_base(p)))
    pipeline = mr.get("head_pipeline") or {}
    if not pipeline:
        return {"sha": mr.get("sha"), "state": "none", "failed": [], "pending": [], "checks": []}
    project = urllib.parse.quote(p["project"], safe="")
    jobs = json.loads(glab(p["host"], f"projects/{project}/pipelines/{pipeline['id']}/jobs?per_page=100"))
    checks = [{"name": j["name"], "status": j["status"], "conclusion": j["status"], "url": j.get("web_url"),
               "id": j["id"], "allow_failure": j.get("allow_failure", False)} for j in jobs]
    return summarize(mr.get("sha"), checks,
                     lambda c: c["status"] in ("created", "pending", "running", "waiting_for_resource", "preparing"),
                     lambda c: c["status"] == "failed" and not c.get("allow_failure"))


def summarize(sha, checks, is_pending, is_failed):
    failed = [c for c in checks if is_failed(c)]
    pending = [c for c in checks if is_pending(c)]
    state = "failed" if failed else "pending" if pending else "passed" if checks else "none"
    return {"sha": sha, "state": state, "failed": failed, "pending": [c["name"] for c in pending], "checks": checks}


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) < 2 or argv[0] not in ("list", "reply", "checks") or (argv[0] == "reply" and len(argv) != 3):
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    try:
        kind, p = parse(argv[1])
        if argv[0] == "list":
            print(json.dumps(gh_list(p) if kind == "github" else gl_list(p), indent=2, ensure_ascii=False))
        elif argv[0] == "checks":
            print(json.dumps(gh_checks(p) if kind == "github" else gl_checks(p), indent=2))
        else:
            text = sys.stdin.read()
            if not text.strip():
                raise Error("reply text is empty (pass it on stdin)")
            ref = gh_reply(p, argv[2], text) if kind == "github" else gl_reply(p, argv[2], text)
            print(f"ok {ref}")
    except Error as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except (KeyError, TypeError, json.JSONDecodeError) as e:
        print(f"error: unexpected response from host ({type(e).__name__}: {e})", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
