#!/usr/bin/env python3
"""Scan the lines a branch adds for likely secrets before it is pushed.

  scan_secrets.py <repo_dir> <base_ref>        e.g. scan_secrets.py codebase/api origin/main

Checks only what `git diff <base_ref>...HEAD` adds, so existing history doesn't produce noise.
Exit 0 = clean, 1 = findings (printed, with the matched value masked), 2 = usage/git error.
If `gitleaks` is installed it is run as well, and its findings count too.

A line can be allowed explicitly with the marker `ai-workspace:allow-secret` (e.g. test fixtures).
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys

PATTERNS = [
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{50,}\b")),
    ("GitLab token", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b")),
    ("Slack token", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}\b")),
    ("Stripe live key", re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{20,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("Anthropic/OpenAI key", re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{32,}\b")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("credentials in URL", re.compile(r"\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s:@]{3,}@[^\s/]+")),
    ("hard-coded secret", re.compile(
        r"(?i)\b\w*(?:password|passwd|pwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|private[_-]?key)"
        r"\w*[\"']?\s*[:=]\s*[\"']([^\"'\s]{8,})[\"']")),
]
PLACEHOLDER = re.compile(r"(?i)(example|sample|dummy|changeme|placeholder|your[_-]|xxx+|\*{3,}|<[^>]+>|\$\{|\{\{|test)")
SENSITIVE_FILES = re.compile(
    r"(^|/)(\.env(\.[^/]*)?|id_rsa|id_ed25519|id_ecdsa|.*\.pem|.*\.p12|.*\.pfx|.*\.keystore|.*\.jks|"
    r"credentials\.json|service-account.*\.json|\.npmrc|\.pypirc|\.netrc)$")
SAFE_FILES = re.compile(r"(^|/)\.env\.(example|sample|template|dist)$")
ALLOW = "ai-workspace:allow-secret"


def mask(value: str) -> str:
    return value[:4] + "…" + value[-2:] if len(value) > 8 else "…"


def git(repo, *args):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if r.returncode:
        print(f"error: git {' '.join(args)}: {r.stderr.strip()}", file=sys.stderr)
        sys.exit(2)
    return r.stdout


def scan(repo: str, base: str) -> list[str]:
    findings = []
    for path in git(repo, "diff", "--name-only", "--diff-filter=AM", f"{base}...HEAD").splitlines():
        if SENSITIVE_FILES.search(path) and not SAFE_FILES.search(path):
            findings.append(f"{path}: sensitive file added to the branch")

    current, line_no = None, 0
    for line in git(repo, "diff", "--unified=0", "--no-color", f"{base}...HEAD").splitlines():
        if line.startswith("+++ "):
            current = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            line_no = int(m.group(1)) - 1 if m else 0
        elif line.startswith("+") and current:
            line_no += 1
            text = line[1:]
            if ALLOW in text:
                continue
            for label, rx in PATTERNS:
                m = rx.search(text)
                if not m:
                    continue
                value = m.group(1) if m.groups() else m.group(0)
                if label in ("hard-coded secret", "credentials in URL") and PLACEHOLDER.search(value):
                    continue
                findings.append(f"{current}:{line_no}: {label} ({mask(value)})")
                break
    return findings


def run_gitleaks(repo: str, base: str) -> list[str]:
    if not shutil.which("gitleaks"):
        return []
    r = subprocess.run(["gitleaks", "git", "--no-banner", "--redact", f"--log-opts={base}..HEAD", repo],
                       capture_output=True, text=True)
    if r.returncode == 1:
        return ["gitleaks reported findings:\n" + (r.stdout or r.stderr).strip()]
    return []


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    repo, base = sys.argv[1], sys.argv[2]
    findings = scan(repo, base) + run_gitleaks(repo, base)
    if not findings:
        print(f"clean: no secrets found in changes since {base}")
        return 0
    print(f"{len(findings)} possible secret(s) in changes since {base}:")
    for f in findings:
        print(f"  - {f}")
    print(f"Remove them (and rotate any real credential), or mark a false positive with '{ALLOW}'.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
