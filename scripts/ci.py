#!/usr/bin/env python3
"""CI adapters for ai-workspace: pipeline status, failure logs and re-runs outside the git host.

  ci.py --provider jenkins --url URL status  --job JOB --branch BRANCH [--sha SHA]
  ci.py --provider jenkins --url URL log     --build BUILD_URL [--tail 200]
  ci.py --provider jenkins --url URL rerun   --job JOB --branch BRANCH
  ci.py --provider custom --status-cmd "..." [--log-cmd "..."] [--rerun-cmd "..."] <op> ...

status prints the same summary shape as review_threads.py checks:
  {"sha", "state": passed|failed|pending|none, "failed": [{name, id, url}], "pending": [...], "checks": [...]}

jenkins: JOB is the job path as shown in Jenkins ("payroll/backend" for folder payroll, job backend).
  Multibranch pipelines are tried first (a sub-job per branch); otherwise the job's recent builds are
  matched by commit. Credentials: env JENKINS_USER and JENKINS_TOKEN (a Jenkins API token).
custom: command templates with {codebase}, {branch}, {sha}, {build}; status may print summary JSON or
  one word (passed / failed / pending). Placeholders are substituted per argument, never through a shell.
Only the Python standard library is used.
"""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tracker import TrackerError as CIError, http, need_env, split_command  # noqa: E402

FAILED = {"FAILURE", "UNSTABLE", "ABORTED", "NOT_BUILT"}
BUILD_TREE = "builds[number,url,result,building,actions[lastBuiltRevision[SHA1]]]{0,30}"


def summary(sha, checks):
    failed = [c for c in checks if c["state"] == "failed"]
    pending = [c["name"] for c in checks if c["state"] == "pending"]
    state = "failed" if failed else "pending" if pending else "passed" if checks else "none"
    return {"sha": sha, "state": state, "failed": failed, "pending": pending, "checks": checks}


# --- jenkins --------------------------------------------------------------------------------

class Jenkins:
    def __init__(self, url):
        if not url:
            raise CIError("jenkins needs --url (ci.url in workspace.yaml)")
        self.base = url.rstrip("/")
        user, token = need_env("JENKINS_USER", "JENKINS_TOKEN")
        self.headers = {"Authorization": "Basic " + base64.b64encode(f"{user}:{token}".encode()).decode()}

    @staticmethod
    def job_path(job):
        parts = [p for p in job.strip("/").split("/") if p and p != "job"]
        if not parts:
            raise CIError("empty --job")
        return "".join(f"/job/{urllib.parse.quote(p, safe='')}" for p in parts)

    @staticmethod
    def branch_segment(branch):
        # Multibranch jobs are named after the branch with "/" encoded as %2F; the URL encodes that again.
        return "/job/" + urllib.parse.quote(urllib.parse.quote(branch, safe=""), safe="")

    def _get(self, path_or_url):
        url = path_or_url if path_or_url.startswith("http") else self.base + path_or_url
        return http("GET", url, headers=self.headers)

    def _builds(self, job, branch):
        """Builds of the branch's multibranch sub-job if it exists, else of the job itself."""
        jp = self.job_path(job)
        try:
            data = self._get(f"{jp}{self.branch_segment(branch)}/api/json?tree={BUILD_TREE}")
            return f"{jp}{self.branch_segment(branch)}", data.get("builds") or [], True
        except CIError as e:
            if "HTTP 404" not in str(e):
                raise
        data = self._get(f"{jp}/api/json?tree={BUILD_TREE}")
        return jp, data.get("builds") or [], False

    @staticmethod
    def build_sha(build):
        for action in build.get("actions") or []:
            sha = ((action or {}).get("lastBuiltRevision") or {}).get("SHA1")
            if sha:
                return sha
        return None

    def status(self, job, branch, sha):
        path, builds, multibranch = self._builds(job, branch)
        build = None
        if sha:
            build = next((b for b in builds if (self.build_sha(b) or "").startswith(sha)), None)
        if build is None and multibranch and builds and not sha:
            build = builds[0]
        if build is None:
            return {**summary(sha, []), "note": f"no Jenkins build found yet for {branch}"
                                                + (f" at {sha[:10]}" if sha else "")}
        state = "pending" if build.get("building") else \
            "failed" if (build.get("result") or "") in FAILED else "passed"
        checks = [{"name": f"{job} #{build.get('number')}", "state": state, "id": build.get("url"),
                   "url": build.get("url"), "result": build.get("result")}]
        if state == "failed":
            checks[0]["failed_stages"] = self._failed_stages(build.get("url", ""))
        return summary(sha or self.build_sha(build), checks)

    def _failed_stages(self, build_url):
        try:  # Pipeline Stage View plugin; optional
            stages = self._get(build_url.rstrip("/") + "/wfapi/describe").get("stages") or []
        except (CIError, AttributeError):
            return []
        return [s.get("name") for s in stages if s.get("status") in ("FAILED", "UNSTABLE", "ABORTED")]

    def log(self, build_url, tail):
        if not build_url.startswith(self.base):
            raise CIError(f"build URL must be on {self.base}")
        url = build_url.rstrip("/") + "/consoleText"
        req_headers = dict(self.headers, Accept="text/plain")
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=req_headers), timeout=60) as r:
                text = r.read().decode(errors="replace")
        except Exception as e:  # noqa: BLE001 - reported as one line
            raise CIError(f"cannot read console log: {e}") from None
        return "\n".join(text.splitlines()[-tail:])

    def rerun(self, job, branch):
        path, _, _ = self._builds(job, branch)
        for endpoint in ("/build", "/buildWithParameters"):
            try:
                http("POST", f"{self.base}{path}{endpoint}", headers=self.headers)
                return f"queued: {self.base}{path}"
            except CIError as e:
                if "HTTP 400" not in str(e) and "HTTP 405" not in str(e):
                    raise
        raise CIError("Jenkins refused to start the build (check job permissions/parameters)")


# --- custom ---------------------------------------------------------------------------------

class Custom:
    def __init__(self, args):
        self.cmds = {"status": args.status_cmd, "log": args.log_cmd, "rerun": args.rerun_cmd}

    def _run(self, op, **values):
        tpl = self.cmds.get(op)
        if not tpl:
            raise CIError(f"custom CI has no --{op}-cmd configured")
        argv = []
        for part in split_command(tpl):
            for k, v in values.items():
                part = part.replace("{" + k + "}", v or "")
            argv.append(part)
        try:
            r = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
        except FileNotFoundError:
            raise CIError(f"command not found: {argv[0]}") from None
        except subprocess.TimeoutExpired:
            raise CIError(f"{argv[0]} timed out after 120s") from None
        if r.returncode:
            raise CIError(r.stderr.strip() or f"{argv[0]} exited {r.returncode}")
        return r.stdout.strip()

    def status(self, codebase, branch, sha):
        out = self._run("status", codebase=codebase, branch=branch, sha=sha)
        try:
            d = json.loads(out)
            if isinstance(d, dict) and "state" in d:
                return {**summary(sha, []), **d}
        except json.JSONDecodeError:
            pass
        word = out.split()[0].lower() if out else ""
        state = {"success": "passed", "passed": "passed", "ok": "passed", "failed": "failed",
                 "failure": "failed", "running": "pending", "pending": "pending"}.get(word)
        if not state:
            raise CIError(f"custom status command printed neither summary JSON nor a known state: {out[:80]!r}")
        return summary(sha, [{"name": codebase, "state": state, "id": "", "url": ""}])

    def log(self, build, tail):
        return "\n".join(self._run("log", build=build).splitlines()[-tail:])

    def rerun(self, codebase, branch):
        return self._run("rerun", codebase=codebase, branch=branch) or "requested"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="ai-workspace CI adapter")
    p.add_argument("--provider", required=True, choices=["jenkins", "custom"])
    p.add_argument("--url")
    p.add_argument("--status-cmd")
    p.add_argument("--log-cmd")
    p.add_argument("--rerun-cmd")
    sub = p.add_subparsers(dest="op", required=True)
    for op in ("status", "rerun"):
        s = sub.add_parser(op)
        s.add_argument("--job", help="jenkins job path")
        s.add_argument("--codebase", default="")
        s.add_argument("--branch", required=True)
        if op == "status":
            s.add_argument("--sha", default="")
    lg = sub.add_parser("log")
    lg.add_argument("--build", required=True, help="jenkins build URL, or the id your custom command expects")
    lg.add_argument("--tail", type=int, default=200)
    a = p.parse_args(argv)
    try:
        if a.provider == "jenkins":
            ci = Jenkins(a.url)
            if a.op in ("status", "rerun") and not a.job:
                raise CIError("jenkins needs --job (ci_job of the codebase)")
            if a.op == "status":
                print(json.dumps(ci.status(a.job, a.branch, a.sha), indent=2))
            elif a.op == "log":
                print(ci.log(a.build, a.tail))
            else:
                print(ci.rerun(a.job, a.branch))
        else:
            ci = Custom(a)
            if a.op == "status":
                print(json.dumps(ci.status(a.codebase, a.branch, a.sha), indent=2))
            elif a.op == "log":
                print(ci.log(a.build, a.tail))
            else:
                print(ci.rerun(a.codebase, a.branch))
    except CIError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"error: unexpected {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
