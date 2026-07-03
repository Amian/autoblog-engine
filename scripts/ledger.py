#!/usr/bin/env python3
"""Topic ledger tooling — the site's persistent memory of covered/planned topics.

  python3 ledger.py seed   --config autoblog.config.json [--repo .] [--backlog FILE]
  python3 ledger.py status --config autoblog.config.json [--repo .]

The ledger lives at <repo>/autoblog/ledger.json:
  {
    "version": 1,
    "generated_at": "YYYY-MM-DD",
    "topics":     [ {slug, title, keyword, cluster, date, status: "covered"} ],
    "candidates": [ {slug, topic, keyword, cluster, status: "candidate", notes} ],
    "rejected":   [ {slug, reason} ]
  }

`seed` inventories every existing post as covered and (optionally) imports a
backlog file (JSON with an "items" list). Re-running seed refreshes the covered
list from the content dir but preserves candidates/rejected entries already
present. Files are truth; the ledger is an index.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import iter_posts, load_config, today

LEDGER_REL = "autoblog/ledger.json"


def load_ledger(repo: Path) -> dict:
    p = repo / LEDGER_REL
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"version": 1, "generated_at": None, "topics": [], "candidates": [], "rejected": []}


def save_ledger(repo: Path, ledger: dict) -> Path:
    p = repo / LEDGER_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    ledger["generated_at"] = today().isoformat()
    p.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def seed(cfg: dict, repo: Path, backlog: str | None) -> int:
    ledger = load_ledger(repo)
    cluster_field = cfg["content"]["frontmatter"]["clusterField"]
    covered = []
    for post in iter_posts(cfg, repo):
        if post.problems:
            print(f"  skipping {post.path.name}: {'; '.join(post.problems)}", file=sys.stderr)
            continue
        covered.append({
            "slug": post.slug,
            "title": str(post.fm.get("title", "")),
            "keyword": str(post.fm.get("priority_keyword", "")),
            "cluster": str(post.fm.get(cluster_field, "")),
            "date": post.date.isoformat(),
            "status": "covered",
        })
    ledger["topics"] = covered

    if backlog:
        bp = repo / backlog
        try:
            items = json.loads(bp.read_text(encoding="utf-8")).get("items", [])
        except (OSError, json.JSONDecodeError) as e:
            print(f"  backlog import skipped ({e})", file=sys.stderr)
            items = []
        covered_slugs = {t["slug"] for t in covered}
        existing_cand = {c["slug"] for c in ledger["candidates"]}
        added = 0
        for item in items:
            slug = item.get("slug", "")
            if not slug or slug in covered_slugs or slug in existing_cand:
                continue
            ledger["candidates"].append({
                "slug": slug,
                "topic": item.get("topic", slug),
                "keyword": item.get("priority_keyword", ""),
                "cluster": item.get("cluster", ""),
                "status": "candidate",
                "notes": item.get("notes", ""),
            })
            added += 1
        print(f"  imported {added} backlog candidates")

    path = save_ledger(repo, ledger)
    print(f"seeded {len(covered)} covered topics, {len(ledger['candidates'])} candidates → {path}")
    return 0


def status(cfg: dict, repo: Path) -> int:
    ledger = load_ledger(repo)
    dates = sorted(t["date"] for t in ledger["topics"] if t.get("date"))
    print(json.dumps({
        "covered": len(ledger["topics"]),
        "candidates": len(ledger["candidates"]),
        "rejected": len(ledger.get("rejected", [])),
        "latest": dates[-1] if dates else None,
        "generated_at": ledger.get("generated_at"),
    }, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["seed", "status"])
    ap.add_argument("--config", required=True)
    ap.add_argument("--repo", default=".")
    ap.add_argument("--backlog", default=None, help="backlog JSON file to import as candidates")
    args = ap.parse_args()
    cfg = load_config(args.config)
    repo = Path(args.repo)
    return seed(cfg, repo, args.backlog) if args.command == "seed" else status(cfg, repo)


if __name__ == "__main__":
    sys.exit(main())
