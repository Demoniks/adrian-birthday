#!/usr/bin/env python3
"""
Build the site and push it to GitHub — GitHub Pages then updates in about a minute.

    python scripts/publish.py
    python scripts/publish.py -m "Final version 🎂"

First time only: create the repo and connect it (see README → "Put it on GitHub Pages").
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build  # noqa: E402

ROOT = build.ROOT


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True)


def pages_url(remote: str) -> str | None:
    m = re.search(r"github\.com[:/]([^/]+)/(.+?)(?:\.git)?/?$", remote.strip())
    if not m:
        return None
    user, repo = m.groups()
    if repo.lower() == f"{user.lower()}.github.io":
        return f"https://{user}.github.io/"
    return f"https://{user}.github.io/{repo}/"


def main() -> None:
    ap = argparse.ArgumentParser(description="Build and publish to GitHub Pages")
    ap.add_argument("-m", "--message", default="Update birthday letter")
    args = ap.parse_args()

    if not shutil.which("git"):
        sys.exit("✗ git isn't installed. Get it from https://git-scm.com/downloads")

    print("Building…")
    try:
        build.build()
    except build.BuildError as e:
        sys.exit(f"✗ {e}")

    if git("rev-parse", "--is-inside-work-tree").returncode != 0:
        sys.exit("✗ This folder isn't a git repo yet. Follow README → 'Put it on GitHub Pages' (first time only).")
    remote = git("remote", "get-url", "origin")
    if remote.returncode != 0:
        sys.exit("✗ No GitHub remote yet. Run:\n   git remote add origin https://github.com/YOUR-USER/YOUR-REPO.git")

    git("add", "-A")
    c = git("commit", "-m", args.message)
    if c.returncode != 0 and "nothing to commit" not in (c.stdout + c.stderr):
        sys.exit(f"✗ git commit failed:\n{c.stderr or c.stdout}")
    print("✓ committed" if c.returncode == 0 else "• nothing new to commit")

    p = git("push")
    if p.returncode != 0 and ("no upstream" in p.stderr or "set-upstream" in p.stderr):
        p = git("push", "-u", "origin", "HEAD")
    if p.returncode != 0:
        sys.exit(f"✗ git push failed:\n{p.stderr}")
    print("✓ pushed to GitHub")

    url = pages_url(remote.stdout.strip())
    if url:
        print(f"\n★ Live in ~1 minute at: {url}")
        print("  (first time? Settings → Pages → Source: 'Deploy from a branch' → main → /docs)")


if __name__ == "__main__":
    main()
