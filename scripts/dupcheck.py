#!/usr/bin/env python3
"""Near-duplicate detection: word-shingle containment between posts.

  python3 dupcheck.py --config autoblog.config.json [--repo .] [--scope future|all]

For each candidate post (default: future-dated — the queue), compare against
every other post in the corpus. Containment = |shingles(A) ∩ shingles(B)| /
min(|A|, |B|), with 8-word shingles over normalized body text. Above
quality.dupContainmentThreshold = duplicate → exit 1.

Containment beats Jaccard here: a short post pasted into a long one still
scores ~1.0. Shared boilerplate (CTA includes, liquid tags) is stripped first.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import iter_posts, load_config, today

SHINGLE = 8


def shingles(body: str) -> set:
    text = re.sub(r"\{%.*?%\}", " ", body)
    text = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    words = text.split()
    return {hash(" ".join(words[i:i + SHINGLE])) for i in range(max(0, len(words) - SHINGLE + 1))}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--repo", default=".")
    ap.add_argument("--scope", choices=["future", "all"], default="future")
    ap.add_argument("--top", type=int, default=5, help="also report the top-N highest overlaps")
    args = ap.parse_args()

    cfg = load_config(args.config)
    threshold = cfg["quality"]["dupContainmentThreshold"]
    posts = [p for p in iter_posts(cfg, Path(args.repo)) if p.slug and p.body]
    now = today()
    candidates = posts if args.scope == "all" else [p for p in posts if p.date > now]
    if not candidates:
        print("no candidate posts to check")
        return 0

    sets = {p.slug: shingles(p.body) for p in posts}
    failures = 0
    scored: list[tuple[float, str, str]] = []
    checked_pairs = set()
    for cand in candidates:
        a = sets[cand.slug]
        if not a:
            continue
        for other in posts:
            if other.slug == cand.slug:
                continue
            pair = tuple(sorted((cand.slug, other.slug)))
            if pair in checked_pairs:
                continue
            checked_pairs.add(pair)
            b = sets[other.slug]
            if not b:
                continue
            containment = len(a & b) / min(len(a), len(b))
            scored.append((containment, cand.slug, other.slug))
            if containment >= threshold:
                print(f"ERROR near-duplicate ({containment:.2f} >= {threshold}): "
                      f"{cand.slug} ↔ {other.slug}")
                failures += 1

    scored.sort(reverse=True)
    if scored:
        print(f"\ntop overlaps (threshold {threshold}):")
        for c, s1, s2 in scored[:args.top]:
            print(f"  {c:.3f}  {s1} ↔ {s2}")
    print(f"checked {len(candidates)} candidates vs {len(posts)}-post corpus: {failures} duplicates")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
