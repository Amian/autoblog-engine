#!/usr/bin/env python3
"""Startup tree guard for autonomous routines. Stdlib only.

The #1 silent-freeze cause is a leftover throwaway file (a cache, a log, a crashed
run's temp output) making `git status` dirty — which halts every routine that guards on
a clean tree. This resolves that safely:

  - Auto-cleans ONLY known-throwaway UNTRACKED artifacts (logs, *.tmp, gsc-latest.json,
    .DS_Store, anything under a tmp/ dir).
  - REFUSES (blocks) on anything real: any modified/added/deleted TRACKED file, or any
    untracked file outside the throwaway allowlist (e.g. a half-written post from a
    crashed run). Those are never auto-deleted — they need a human + an email.

  python3 treeguard.py --repo REPO [--clean]

Exit 0: tree is clean, or was cleaned of throwaway artifacts only → caller may proceed.
Exit 2: real changes remain → prints them; the caller must STOP and email the owner.
Exit 1: not a git repo / git error.

Design bias: when unsure, BLOCK. The worst case of a bug here must be "failed to clean
(stops + emails)", never "deleted real work".
"""
from __future__ import annotations

import argparse
import subprocess
import sys


def is_throwaway(path: str) -> bool:
    p = path.strip().strip('"')
    return (
        p.endswith(".log")
        or p.endswith(".tmp")
        or p.endswith("/gsc-latest.json")
        or p == "gsc-latest.json"
        or p.endswith("/.DS_Store")
        or p == ".DS_Store"
        or p.startswith("tmp/")
        or "/tmp/" in p
    )


def git(repo: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--clean", action="store_true", help="actually remove throwaway artifacts")
    args = ap.parse_args()

    st = git(args.repo, "status", "--porcelain")
    if st.returncode != 0:
        print(f"treeguard: git error: {st.stderr.strip()}", file=sys.stderr)
        return 1
    lines = [ln for ln in st.stdout.splitlines() if ln.strip()]
    if not lines:
        print("treeguard: clean")
        return 0

    safe, blockers = [], []
    for ln in lines:
        xy, path = ln[:2], ln[3:]
        # rename form "old -> new": guard the new path
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        untracked = xy == "??"
        if untracked and is_throwaway(path):
            safe.append(path)
        else:
            blockers.append(ln)

    if blockers:
        print("treeguard: BLOCKED — real changes present (not auto-cleaning):")
        for b in blockers:
            print(f"  {b}")
        if safe:
            print(f"  (+{len(safe)} throwaway files left untouched while blocked)")
        return 2

    # only throwaway artifacts remain
    if args.clean:
        for path in safe:
            git(args.repo, "clean", "-fq", "--", path)
        # verify we actually reached clean
        again = git(args.repo, "status", "--porcelain").stdout.strip()
        if again:
            print("treeguard: BLOCKED — still dirty after cleaning throwaway files:")
            print("  " + again.replace("\n", "\n  "))
            return 2
        print(f"treeguard: cleaned {len(safe)} throwaway artifact(s) → tree clean")
        return 0
    else:
        print(f"treeguard: {len(safe)} throwaway artifact(s) (run --clean to remove):")
        for s in safe:
            print(f"  {s}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
