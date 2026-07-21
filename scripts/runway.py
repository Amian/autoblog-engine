#!/usr/bin/env python3
"""Report the blog queue's runway: how many days of scheduled posts remain.

  python3 runway.py --config autoblog.config.json [--repo .]

Prints a JSON summary and, inside GitHub Actions, writes step outputs:
  days          integer days of queue left (0 if the queue is already dry)
  dry_date      first date with no post scheduled
  needs_refill  "true" if days < cadence.refillThresholdDays
  below_min     "true" if days < quality.minRunwayDays  (watchdog threshold)
Exit code is always 0 on success — thresholds are outputs, not failures.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import github_output, iter_posts, load_config, today


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--repo", default=".")
    args = ap.parse_args()

    cfg = load_config(args.config)
    repo = Path(args.repo)
    # Only posts that can actually publish count as runway: the site's blog
    # loader (packages/theme/src/lib/blog.ts) ships a post only when
    # review_state == "fact-checked", so a draft (e.g. a far-future template
    # post) must never inflate the queue gauge.
    posts = [
        p
        for p in iter_posts(cfg, repo)
        if p.date != p.date.min and p.fm.get("review_state") == "fact-checked"
    ]
    now = today()

    if not posts:
        latest = None
        days = 0
        dry = now
    else:
        latest = max(p.date for p in posts)
        days = max(0, (latest - now).days)
        dry = max(latest + timedelta(days=1), now)

    needs_refill = days < cfg["cadence"]["refillThresholdDays"]
    below_min = days < cfg["quality"]["minRunwayDays"]

    summary = {
        "posts": len(posts),
        "latest_post": latest.isoformat() if latest else None,
        "days": days,
        "dry_date": dry.isoformat(),
        "needs_refill": needs_refill,
        "below_min": below_min,
        "refill_threshold_days": cfg["cadence"]["refillThresholdDays"],
        "min_runway_days": cfg["quality"]["minRunwayDays"],
    }
    print(json.dumps(summary, indent=2))
    github_output(
        days=days,
        dry_date=dry.isoformat(),
        needs_refill=str(needs_refill).lower(),
        below_min=str(below_min).lower(),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
