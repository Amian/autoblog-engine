#!/usr/bin/env python3
"""Verify every cited source URL in post frontmatter actually resolves. Stdlib only.

  python3 sourcecheck.py --config autoblog.config.json [--repo .] [--scope future|all]

A post that cites a dead or wrong URL is unpublishable under unattended auto-merge —
a broken citation is exactly the kind of quiet quality failure a human reviewer used to
catch. This gate makes it deterministic.

For each in-scope post it reads the frontmatter `sources` list (flat strings, format
"Title :: https://url" — the factory contract), extracts each URL, and issues a HEAD
(falling back to GET) request. Non-2xx/3xx, connection failures, and malformed source
strings are reported per post.

Exit 0 = every source resolved. Exit 1 = at least one dead/malformed source (the caller
fixes the citation or replaces the topic before publishing). `--warn-only` downgrades to
exit 0 with the report still printed (useful when a source host blocks bots — a 403 is
often the venue, not a dead link; the caller eyeballs those).

Network flakiness is retried once; a genuinely unreachable host after retry is a
failure, not a skip — the whole point is to not ship broken citations.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import iter_posts, load_config, today

UA = "Mozilla/5.0 (compatible; autoblog-sourcecheck/1.0)"
URL_RE = re.compile(r"https?://\S+")
# hosts that habitually 403 bots but are legitimate citations — reported as "blocked", not failed
KNOWN_BOT_WALLS = ("jstor.org", "sciencedirect.com", "tandfonline.com", "springer.com")


def extract_url(source: str) -> str | None:
    # contract is "Title :: https://url" (URL last); tolerate a bare URL or trailing text
    m = URL_RE.search(source)
    if not m:
        return None
    url = m.group(0).rstrip(".,;'\"")
    # preserve balanced parens (Wikipedia disambiguation, e.g. Mount_Adams_(Washington));
    # only strip a trailing ) that has no matching ( — real sentence punctuation
    while url.endswith(")") and url.count("(") < url.count(")"):
        url = url[:-1]
    return url or None


def check_url(url: str, timeout=15) -> tuple[str, int | None, str]:
    """Return (status, http_code, detail). status in ok|blocked|dead."""
    host = url.split("://", 1)[-1].split("/", 1)[0].lower()
    for method in ("HEAD", "GET"):
        last = None
        for attempt in (1, 2):
            try:
                req = urllib.request.Request(url, method=method, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return "ok", resp.status, ""
            except urllib.error.HTTPError as e:
                if e.code in (403, 405, 429) and method == "HEAD":
                    break  # retry as GET
                if e.code in (403, 429) and any(w in host for w in KNOWN_BOT_WALLS):
                    return "blocked", e.code, "known bot-wall host"
                if e.code in (401, 403, 429):
                    return "blocked", e.code, "auth/bot wall"
                return "dead", e.code, e.reason if isinstance(e.reason, str) else str(e.reason)
            except (urllib.error.URLError, TimeoutError, ValueError) as e:
                last = e
                continue
        if last and method == "GET":
            return "dead", None, str(getattr(last, "reason", last))
    return "dead", None, "unreachable"


def in_scope(post, scope: str) -> bool:
    if scope == "all":
        return True
    d = post.fm.get("date")
    try:
        from _common import parse_date
        return parse_date(d) >= today()
    except Exception:
        return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", required=True)
    ap.add_argument("--repo", default=".")
    ap.add_argument("--scope", choices=["future", "all"], default="future")
    ap.add_argument("--warn-only", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    cfg = load_config(args.config)
    posts = [p for p in iter_posts(cfg, Path(args.repo)) if in_scope(p, args.scope)]

    failures, blocked, checked, seen = [], [], 0, {}
    report = []
    for post in posts:
        sources = post.fm.get("sources") or []
        if isinstance(sources, str):
            sources = [sources]
        for src in sources:
            url = extract_url(str(src))
            if not url:
                failures.append((post.slug, str(src), "no URL in source string"))
                continue
            if url not in seen:
                seen[url] = check_url(url)
                checked += 1
            status, code, detail = seen[url]
            if status == "dead":
                failures.append((post.slug, url, f"HTTP {code} {detail}".strip()))
            elif status == "blocked":
                blocked.append((post.slug, url, f"HTTP {code} {detail}".strip()))

    for slug, url, why in failures:
        report.append(f"DEAD    {slug}: {url}  ({why})")
    for slug, url, why in blocked:
        report.append(f"BLOCKED {slug}: {url}  ({why}) — likely the host, eyeball it")

    if args.json:
        print(json.dumps({"checked_urls": checked, "posts": len(posts),
                          "dead": [{"slug": s, "url": u, "why": w} for s, u, w in failures],
                          "blocked": [{"slug": s, "url": u, "why": w} for s, u, w in blocked]}, indent=1))
    else:
        print("\n".join(report) if report else "all sources resolved ✓")
        print(f"\n{checked} unique URLs across {len(posts)} posts · "
              f"{len(failures)} dead · {len(blocked)} blocked(host)", file=sys.stderr)

    if failures and not args.warn_only:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
