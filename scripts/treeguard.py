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

  python3 treeguard.py --repo REPO [--clean] [--park]

With --park, real changes no longer halt the caller: they are committed onto a
salvage/auto-park-<date> branch (and pushed when a remote exists), after which the
working tree is returned to HEAD and the caller proceeds. Nothing is deleted — the
work is recoverable from that branch — so an autonomous routine never freezes just
because someone left edits behind. A dirty tree used to starve every queue for days;
parking converts that hard halt into a self-healing step.

Exit 0: tree is clean, was cleaned of throwaway artifacts only, or (with --park) real
        changes were parked onto a branch → caller may proceed.
Exit 2: real changes remain → prints them; the caller must STOP and email the owner.
Exit 1: not a git repo / git error.

Design bias: when unsure, BLOCK. The worst case of a bug here must be "failed to clean
(stops + emails)" or "parked work onto a branch", never "deleted real work".
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


def in_progress_operation(repo: str) -> str | None:
    """Merge/rebase/bisect in flight — parking would corrupt it. Never park then."""
    for name, label in (
        ("MERGE_HEAD", "a merge"),
        ("REBASE_HEAD", "a rebase"),
        ("CHERRY_PICK_HEAD", "a cherry-pick"),
        ("BISECT_LOG", "a bisect"),
    ):
        r = git(repo, "rev-parse", "--verify", "--quiet", name)
        if r.returncode == 0 and r.stdout.strip():
            return label
    d = git(repo, "rev-parse", "--git-path", "rebase-merge")
    if d.returncode == 0:
        import os
        if os.path.isdir(os.path.join(repo, d.stdout.strip())) or os.path.isdir(d.stdout.strip()):
            return "a rebase"
    return None


def park(repo: str, blockers: list[str]) -> int:
    """Commit every real change onto a salvage branch, then return the tree to HEAD.

    Uses plumbing (write-tree/commit-tree) so no branch switch is needed and a
    conflicting checkout can never strand the work half-moved.
    """
    busy = in_progress_operation(repo)
    if busy:
        print(f"treeguard: BLOCKED — {busy} is in progress; refusing to park.")
        for b in blockers:
            print(f"  {b}")
        return 2

    import datetime
    stamp = datetime.date.today().isoformat()
    head = git(repo, "rev-parse", "--short", "HEAD").stdout.strip()
    branch = f"salvage/auto-park-{stamp}-{head}"
    # a second park on the same day must not collide
    n = 2
    while git(repo, "rev-parse", "--verify", "--quiet", branch).returncode == 0:
        branch = f"salvage/auto-park-{stamp}-{head}-{n}"
        n += 1

    # Record which untracked paths we are about to absorb, so we clean exactly those.
    untracked = [
        ln[3:] for ln in git(repo, "status", "--porcelain").stdout.splitlines()
        if ln.startswith("??")
    ]

    if git(repo, "add", "-A").returncode != 0:
        print("treeguard: BLOCKED — could not stage changes to park them.")
        return 2
    tree = git(repo, "write-tree").stdout.strip()
    if not tree:
        print("treeguard: BLOCKED — could not write a tree to park.")
        git(repo, "reset", "-q")
        return 2
    msg = (
        f"salvage: auto-parked uncommitted work ({stamp})\n\n"
        f"An autonomous routine found {len(blockers)} real change(s) in the working\n"
        "tree. Rather than halt (which starves content queues) or delete them, they\n"
        "were committed here and the tree was returned to HEAD.\n\n"
        "Nothing is lost: recover with\n"
        f"  git checkout {branch}\n"
        f"  git diff {head}..{branch}\n"
    )
    commit = git(repo, "commit-tree", tree, "-p", "HEAD", "-m", msg).stdout.strip()
    if not commit:
        print("treeguard: BLOCKED — could not create the park commit.")
        git(repo, "reset", "-q")
        return 2
    if git(repo, "branch", branch, commit).returncode != 0:
        print(f"treeguard: BLOCKED — could not create branch {branch}.")
        git(repo, "reset", "-q")
        return 2

    # Work is now safely in a commit on `branch`; return the tree to HEAD.
    git(repo, "reset", "-q", "--hard", "HEAD")
    for u in untracked:
        git(repo, "clean", "-fdq", "--", u)

    still = git(repo, "status", "--porcelain").stdout.strip()
    if still:
        print("treeguard: BLOCKED — tree still dirty after parking:")
        print("  " + still.replace("\n", "\n  "))
        print(f"  (work IS preserved on {branch})")
        return 2

    pushed = False
    if git(repo, "remote").stdout.strip():
        pushed = git(repo, "push", "-q", "origin", branch).returncode == 0

    print(f"treeguard: PARKED {len(blockers)} real change(s) onto {branch}"
          + (" (pushed)" if pushed else " (local only — push failed or no remote)"))
    print(f"  recover with: git diff {head}..{branch}")
    print(f"PARK_BRANCH={branch}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--clean", action="store_true", help="actually remove throwaway artifacts")
    ap.add_argument("--park", action="store_true",
                    help="instead of blocking on real changes, commit them to a salvage branch "
                         "and return the tree to HEAD so the routine can proceed")
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
        if args.park:
            # clear throwaway noise first so it never lands in the salvage commit
            if args.clean:
                for path in safe:
                    git(args.repo, "clean", "-fq", "--", path)
            print("treeguard: real changes present — parking them (nothing is deleted):")
            for b in blockers:
                print(f"  {b}")
            return park(args.repo, blockers)
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
