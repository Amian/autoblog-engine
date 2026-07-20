#!/usr/bin/env python3
"""Google Search Console reader for the audit/improvement loop.

  python3 gsc.py sites
  python3 gsc.py report --config autoblog.config.json [--days 90] [--out gsc.json]

Subcommands
  sites    List every property the service account can read (proves the grant).
  report   For the config's site.url, pull last-N-day query + page performance and
           classify each blog post: winner / quick-win / dormant. Also surfaces the
           top "growth-gap" queries — real impressions we rank poorly for — as
           candidate topics. Writes JSON (--out) and prints a human summary.

Auth: a service-account JSON key. Resolution order:
  --key PATH  →  $GSC_CREDENTIALS (path)  →  a machine default. Needs the
  `google-auth` library; if the current interpreter lacks it, the script re-execs
  with a known-good one (env $GSC_PYTHON or a discovered venv). Scope:
  webmasters.readonly.

Read-only. Never edits posts. Fails soft: missing key / disabled API / no data
prints a clear note and exits 0 (unless --strict) so the audit degrades, never breaks.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import iter_posts, load_config, today, url_for  # stdlib-only helpers

DEFAULT_KEY = "/Users/anum/Development/AntiqueHybrid/play-service-account.json"
# Portfolio sites were verified by different service accounts over time (the older
# AntiqueHybrid key owns trystampo/peakspotter/identifyantiques; the shared factory
# key owns the 2026-07 sites). Try every key we have before declaring "no grant".
FALLBACK_KEYS = [
    "/Users/anum/.config/google-play/play-console-api.json",
]
SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
CANDIDATE_PYTHONS = [
    os.environ.get("GSC_PYTHON", ""),
    "/Users/anum/.claude/skills/play-store-submit/.venv/bin/python",
]


class Skip(Exception):
    """Non-fatal: print note, exit 0 (or 1 with --strict)."""


def _ensure_google_auth():
    """google-auth needs a crypto lib (not stdlib); re-exec with an interpreter that has it."""
    try:
        import google.oauth2.service_account  # noqa: F401
        return
    except ImportError:
        pass
    if os.environ.get("_GSC_REEXECED"):
        raise Skip("google-auth not available in any candidate interpreter "
                   "(pip install google-auth, or set $GSC_PYTHON)")
    for py in CANDIDATE_PYTHONS:
        if py and Path(py).exists() and os.path.realpath(py) != os.path.realpath(sys.executable):
            os.environ["_GSC_REEXECED"] = "1"
            os.execv(py, [py, *sys.argv])  # replaces this process
    raise Skip("google-auth not available (pip install google-auth, or set $GSC_PYTHON)")


def _session(key_path: str):
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    creds = service_account.Credentials.from_service_account_file(key_path, scopes=[SCOPE])
    return AuthorizedSession(creds), creds.service_account_email


def resolve_keys(args) -> list[str]:
    """Every usable key, most-specific first. --key (or $GSC_CREDENTIALS) wins but does
    not suppress the others: a property may be granted to any one of our accounts."""
    keys: list[str] = []
    cands = [getattr(args, "key", None), os.environ.get("GSC_CREDENTIALS"), DEFAULT_KEY, *FALLBACK_KEYS]
    for cand in cands:
        if cand and Path(cand).is_file() and cand not in keys:
            keys.append(cand)
    if not keys:
        raise Skip("no service-account key (pass --key, set $GSC_CREDENTIALS, or place the default)")
    return keys


def resolve_key(args) -> str:
    return resolve_keys(args)[0]


def list_sites(sess) -> list[dict]:
    r = sess.get("https://www.googleapis.com/webmasters/v3/sites")
    if r.status_code == 403 and "has not been used" in r.text:
        raise Skip("Search Console API disabled on the key's GCP project — enable it in the Cloud console")
    if r.status_code != 200:
        raise Skip(f"sites.list HTTP {r.status_code}: {r.text[:160]}")
    return r.json().get("siteEntry", [])


def match_property(sites: list[dict], site_url: str) -> str | None:
    host = site_url.split("://", 1)[-1].strip("/").lower()
    forms = {f"sc-domain:{host}", f"https://{host}/", f"http://{host}/"}
    visible = {s["siteUrl"] for s in sites}
    for f in forms:
        if f in visible:
            return f
    # also match a domain property covering this host
    for s in sites:
        if s["siteUrl"] == f"sc-domain:{host}":
            return s["siteUrl"]
    return None


def query(sess, prop: str, start: str, end: str, dimensions: list[str], row_limit=1000) -> list[dict]:
    enc = prop.replace("%", "%25").replace("/", "%2F").replace(":", "%3A")
    url = f"https://www.googleapis.com/webmasters/v3/sites/{enc}/searchAnalytics/query"
    r = sess.post(url, json={"startDate": start, "endDate": end,
                             "dimensions": dimensions, "rowLimit": row_limit})
    if r.status_code != 200:
        raise Skip(f"searchAnalytics HTTP {r.status_code}: {r.text[:160]}")
    return r.json().get("rows", [])


def classify_page(row: dict, published: date | None, now: date) -> str:
    pos, impr, clicks = row["position"], row["impressions"], row["clicks"]
    age_days = (now - published).days if published else None
    if pos <= 10 and clicks > 0:
        return "winner"
    if impr >= 10 and clicks == 0 and pos <= 20:
        return "quick-win"          # ranks + demand, no clicks → title/meta fix
    if pos <= 20 and impr >= 20 and (clicks / impr) < 0.01:
        return "quick-win"          # weak CTR for the position
    if age_days is not None and age_days >= 180 and impr < 3:
        return "dormant"            # old + invisible → prune candidate
    return "steady"


def cmd_sites(args) -> int:
    out = []
    for key in resolve_keys(args):
        sess, sa = _session(key)
        sites = list_sites(sess)
        print(f"service account: {sa}")
        for s in sites:
            print(f"  {s['siteUrl']:42} {s.get('permissionLevel')}")
        out.append({"service_account": sa, "sites": sites})
    print(json.dumps({"accounts": out}, indent=1)) if getattr(args, "json", False) else None
    return 0


def cmd_report(args) -> int:
    cfg = load_config(args.config)
    repo = Path(args.repo)
    site_url = (cfg.get("site") or {}).get("url", "")
    if not site_url:
        raise Skip(f"config {args.config} has no site.url")

    sess = prop = None
    tried = []
    for key in resolve_keys(args):
        cand_sess, sa = _session(key)
        tried.append(sa)
        cand_prop = match_property(list_sites(cand_sess), site_url)
        if cand_prop:
            sess, sa_used, prop = cand_sess, sa, cand_prop
            break
    if not prop:
        raise Skip(f"no GSC property matches {site_url} for any of {', '.join(tried)} "
                   f"— check the grant on that property")
    sa = sa_used

    end = today()
    start = end - timedelta(days=args.days)
    s, e = start.isoformat(), end.isoformat()

    pages = query(sess, prop, s, e, ["page"])
    queries = query(sess, prop, s, e, ["query"])
    page_queries = query(sess, prop, s, e, ["page", "query"])

    # published dates from local post files, keyed by URL path (e.g. /blog/<slug>)
    pub: dict[str, date] = {}
    for p in iter_posts(cfg, repo):
        if p.date and p.date != date.min:
            pub[url_for(cfg, p.slug).rstrip("/")] = p.date

    def path_of(url: str) -> str:
        return "/" + url.split("://", 1)[-1].split("/", 1)[-1].rstrip("/") if "://" in url else url.rstrip("/")

    buckets = {"winner": [], "quick-win": [], "dormant": [], "steady": []}
    for row in pages:
        url = row["keys"][0]
        published = pub.get(path_of(url)) or pub.get(url.rstrip("/"))
        cls = classify_page(row, published, end)
        # best query for this page (for a title/meta rewrite target)
        best_q = None
        for pq in page_queries:
            if pq["keys"][0] == url:
                if best_q is None or pq["impressions"] > best_q["impressions"]:
                    best_q = {"query": pq["keys"][1], "impressions": pq["impressions"],
                              "clicks": pq["clicks"], "position": round(pq["position"], 1)}
        buckets[cls].append({
            "url": url, "clicks": int(row["clicks"]), "impressions": int(row["impressions"]),
            "ctr": round(row["ctr"], 4), "position": round(row["position"], 1),
            "top_query": best_q,
        })

    # growth gaps: queries with real impressions where we rank poorly (>10) and don't win
    won_qs = {b["top_query"]["query"] for b in buckets["winner"] if b["top_query"]}
    gaps = sorted(
        ({"query": r["keys"][0], "impressions": int(r["impressions"]), "clicks": int(r["clicks"]),
          "position": round(r["position"], 1)}
         for r in queries
         if r["impressions"] >= 5 and r["position"] > 10 and r["keys"][0] not in won_qs),
        key=lambda x: -x["impressions"])[:25]

    for k in buckets:
        buckets[k].sort(key=lambda b: -b["impressions"])

    result = {
        "skipped": False, "site": site_url, "property": prop, "service_account": sa,
        "window_days": args.days, "start": s, "end": e,
        "counts": {k: len(v) for k, v in buckets.items()},
        "quick_wins": buckets["quick-win"], "winners": buckets["winner"],
        "dormant_candidates": buckets["dormant"], "growth_gap_queries": gaps,
    }
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=1) + "\n")
        print(f"wrote {args.out}", file=sys.stderr)

    print(f"\n{site_url}  ({prop})  last {args.days}d")
    print(f"  winners {len(buckets['winner'])} · quick-wins {len(buckets['quick-win'])} · "
          f"dormant {len(buckets['dormant'])} · steady {len(buckets['steady'])}")
    if buckets["quick-win"]:
        print("\n  QUICK WINS (rank + demand, weak clicks → rewrite title/meta):")
        for b in buckets["quick-win"][:10]:
            tq = b["top_query"]
            print(f"    {b['url']}")
            print(f"      pos {b['position']} · {b['impressions']} impr · {b['clicks']} clicks"
                  + (f"  →  \"{tq['query']}\" (pos {tq['position']})" if tq else ""))
    if gaps:
        print("\n  GROWTH-GAP QUERIES (demand we don't win — candidate topics):")
        for g in gaps[:10]:
            print(f"    {g['impressions']:>4} impr · pos {g['position']:>5} · {g['query']}")
    if not args.out:
        print("\n" + json.dumps(result, indent=1))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("sites", help="list accessible properties")
    p.add_argument("--key"); p.add_argument("--json", action="store_true"); p.add_argument("--strict", action="store_true")

    p = sub.add_parser("report", help="performance + classification for a site")
    p.add_argument("--config", required=True); p.add_argument("--repo", default=".")
    p.add_argument("--days", type=int, default=90); p.add_argument("--key")
    p.add_argument("--out"); p.add_argument("--strict", action="store_true")

    args = ap.parse_args()
    try:
        _ensure_google_auth()
        return {"sites": cmd_sites, "report": cmd_report}[args.cmd](args)
    except Skip as e:
        print(f"\n⚠️  GSC {args.cmd.upper()} SKIPPED: {e}", file=sys.stderr)
        if getattr(args, "out", None):
            Path(args.out).write_text(json.dumps({"skipped": True, "reason": str(e)}) + "\n")
        print(json.dumps({"skipped": True, "reason": str(e)}))
        return 1 if getattr(args, "strict", False) else 0


if __name__ == "__main__":
    sys.exit(main())
