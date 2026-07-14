#!/usr/bin/env python3
"""Real keyword data from DataForSEO for topic research. Stdlib only.

  python3 keywords.py check
  python3 keywords.py vet   --keywords-file tmp/candidates.txt --config autoblog.config.json
  python3 keywords.py vet   --keywords "mountain identifier app, what mountain is that"
  python3 keywords.py ideas --seed "mountain identifier" --limit 100

Subcommands
  check   Auth + account balance (free endpoint). Always safe to run.
  vet     Batch-validate candidate keywords: search volume, keyword difficulty,
          search intent — one Labs keyword_overview call for up to 700 keywords,
          plus one Google Ads search_volume fallback call for keywords the Labs
          database doesn't know. Results are cached (default TTL 180 days) so
          repeat keywords across refills cost nothing.
  ideas   Expand seed keywords into ranked candidates via Labs
          keyword_suggestions (each row already includes volume/KD/intent).

Credentials: DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD from the environment, else
parsed from ~/.claude/.env. Missing credentials, a dead network, or an empty
balance must NEVER break a refill: every failure prints a loud
"KEYWORDS <CMD> SKIPPED" banner, writes {"skipped": true, ...} to --out, and
exits 0 so the calling agent falls back to heuristic topic selection.
Pass --strict to turn those skips into exit 1 (interactive use).

Cost control: every DataForSEO response reports its actual `cost`; the script
sums and prints it, refuses to start when the projected spend exceeds the
remaining balance, and stops issuing calls once --max-cost (default $0.50) is
reached. Typical vet of a 100-keyword pool: ~$0.02–0.08.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

API = "https://api.dataforseo.com/v3"
DEFAULT_LOCATION = 2840  # United States
DEFAULT_LANGUAGE = "en"
CACHE_TTL_DAYS = 180
GLOBAL_CACHE = Path.home() / ".cache" / "dataforseo" / "keywords-cache.json"
# Conservative pre-flight estimates ($) used only to guard the balance;
# actual spend is read back from each response's `cost` field.
EST_BASE, EST_PER_KW = 0.02, 0.0003


class Skip(Exception):
    """Non-fatal: print the banner, emit skipped output, exit 0 (or 1 with --strict)."""


# ---------------------------------------------------------------- credentials

def load_credentials() -> tuple[str, str]:
    login = os.environ.get("DATAFORSEO_LOGIN", "").strip()
    password = os.environ.get("DATAFORSEO_PASSWORD", "").strip()
    if login and password:
        return login, password
    env_file = Path.home() / ".claude" / ".env"
    if env_file.is_file():
        pairs = {}
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            line = re.sub(r"^export\s+", "", line)
            if "=" in line:
                k, _, v = line.partition("=")
                pairs[k.strip()] = v.strip().strip("'\"")
        login = login or pairs.get("DATAFORSEO_LOGIN", "")
        password = password or pairs.get("DATAFORSEO_PASSWORD", "")
    if not (login and password):
        raise Skip("no DataForSEO credentials (env DATAFORSEO_LOGIN/PASSWORD or ~/.claude/.env)")
    return login, password


# ----------------------------------------------------------------- API client

class Client:
    def __init__(self, login: str, password: str):
        token = base64.b64encode(f"{login}:{password}".encode()).decode()
        self.headers = {"Authorization": f"Basic {token}", "Content-Type": "application/json"}
        self.spent = 0.0  # actual $ spent by this process, from response costs

    def call(self, path: str, payload=None) -> dict:
        url = f"{API}/{path}"
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, headers=self.headers,
                                     method="POST" if data else "GET")
        last_err = None
        for attempt in (1, 2):
            try:
                with urllib.request.urlopen(req, timeout=90) as resp:
                    body = json.loads(resp.read().decode())
                break
            except urllib.error.HTTPError as e:
                # 4xx/5xx still carry a DataForSEO JSON body with the real reason
                try:
                    detail = json.loads(e.read().decode())
                    raise Skip(f"DataForSEO {detail.get('status_code')} on {path}: "
                               f"{detail.get('status_message')}")
                except (json.JSONDecodeError, UnicodeDecodeError):
                    raise Skip(f"DataForSEO HTTP {e.code} on {path}")
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
                last_err = e
                if attempt == 2:
                    raise Skip(f"DataForSEO unreachable ({path}): {last_err}")
        if body.get("status_code") != 20000:
            raise Skip(f"DataForSEO error {body.get('status_code')} on {path}: {body.get('status_message')}")
        self.spent += float(body.get("cost") or 0.0)
        task = (body.get("tasks") or [{}])[0]
        if task.get("status_code") not in (20000, None):
            raise Skip(f"DataForSEO task error {task.get('status_code')} on {path}: {task.get('status_message')}")
        return task

    def balance(self) -> tuple[str, float]:
        task = self.call("appendix/user_data")  # free
        r = (task.get("result") or [{}])[0]
        return r.get("login", "?"), float((r.get("money") or {}).get("balance") or 0.0)


# --------------------------------------------------------------------- cache

def cache_path(args) -> Path:
    if getattr(args, "cache", None):
        return Path(args.cache)
    if getattr(args, "config", None):
        return Path(args.config).resolve().parent / "autoblog" / "keywords-cache.json"
    return GLOBAL_CACHE


def load_cache(path: Path) -> dict:
    if path.is_file():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            print(f"warning: unreadable cache {path}, starting fresh", file=sys.stderr)
    return {}


def save_cache(path: Path, cache: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=1, sort_keys=True) + "\n")


def cache_key(kw: str, location: int, language: str) -> str:
    return f"{kw.lower()}|{location}|{language}"


def is_fresh(entry: dict, ttl_days: int) -> bool:
    try:
        checked = datetime.fromisoformat(entry["checked_at"])
    except (KeyError, ValueError):
        return False
    return (datetime.now(timezone.utc) - checked).days < ttl_days


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------------- helpers

def read_keywords(args) -> list[str]:
    kws: list[str] = []
    if getattr(args, "keywords", None):
        kws += [k.strip() for k in args.keywords.split(",")]
    if getattr(args, "keywords_file", None):
        for line in Path(args.keywords_file).read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                kws.append(line)
    # dedupe, preserve order, normalise whitespace
    seen, out = set(), []
    for k in kws:
        k = re.sub(r"\s+", " ", k).strip()
        if k and k.lower() not in seen:
            seen.add(k.lower())
            out.append(k)
    if not out:
        raise Skip("no keywords given (--keywords or --keywords-file)")
    if len(out) > 700:
        print(f"warning: {len(out)} keywords, truncating to 700 (one-request limit)", file=sys.stderr)
        out = out[:700]
    return out


def guard_cost(client: Client, n_keywords: int, max_cost: float) -> None:
    """Refuse to spend when the projected cost exceeds balance or --max-cost."""
    est = EST_BASE + EST_PER_KW * n_keywords
    login, balance = client.balance()
    print(f"account {login} · balance ${balance:.2f} · projected ≤ ${est:.2f}", file=sys.stderr)
    if balance <= 0.05:
        raise Skip(f"DataForSEO balance exhausted (${balance:.2f}) — top up at app.dataforseo.com")
    if est > balance:
        raise Skip(f"projected cost ${est:.2f} exceeds balance ${balance:.2f} — top up first")
    if est > max_cost:
        raise Skip(f"projected cost ${est:.2f} exceeds --max-cost ${max_cost:.2f}")
    if balance < 5.0:
        print(f"⚠️  LOW BALANCE ${balance:.2f} — top up soon (~$50 recommended)", file=sys.stderr)


def row_from_overview(item: dict) -> dict:
    info = item.get("keyword_info") or {}
    props = item.get("keyword_properties") or {}
    intent = item.get("search_intent_info") or {}
    return {
        "volume": info.get("search_volume"),
        "cpc": info.get("cpc"),
        "competition": info.get("competition"),
        "kd": props.get("keyword_difficulty"),
        "intent": intent.get("main_intent"),
    }


def verdict(row: dict, min_volume: int) -> str:
    v = row.get("volume")
    if v is None:
        return "no-data"
    if v >= min_volume:
        return "ok"
    if v >= 10:
        return "thin"
    return "dead"


def print_table(rows: dict, min_volume: int) -> None:
    width = min(max((len(k) for k in rows), default=10) + 2, 52)
    print(f"\n{'keyword':<{width}}{'volume':>8}{'kd':>5}  {'intent':<14}{'verdict'}")
    for kw in sorted(rows, key=lambda k: -(rows[k].get('volume') or 0)):
        r = rows[kw]
        vol = "-" if r.get("volume") is None else str(r["volume"])
        kd = "-" if r.get("kd") is None else str(r["kd"])
        print(f"{kw[:width-2]:<{width}}{vol:>8}{kd:>5}  {(r.get('intent') or '-'):<14}{verdict(r, min_volume)}")


def emit(args, payload: dict) -> None:
    text = json.dumps(payload, indent=1)
    if getattr(args, "out", None):
        Path(args.out).write_text(text + "\n")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(text)


# --------------------------------------------------------------- subcommands

def cmd_check(args) -> int:
    client = Client(*load_credentials())
    login, balance = client.balance()
    print(json.dumps({"login": login, "balance": balance}))
    if balance < 5.0:
        print(f"⚠️  LOW BALANCE ${balance:.2f} — vet runs cost ~$0.02–0.08 each; top up ~$50 "
              f"at app.dataforseo.com before scaling content research", file=sys.stderr)
    return 0


def cmd_vet(args) -> int:
    keywords = read_keywords(args)
    cpath = cache_path(args)
    cache = load_cache(cpath)
    rows: dict[str, dict] = {}
    missing: list[str] = []
    for kw in keywords:
        entry = cache.get(cache_key(kw, args.location_code, args.language))
        if entry and is_fresh(entry, args.cache_ttl_days):
            rows[kw] = entry
        else:
            missing.append(kw)
    print(f"{len(keywords)} keywords: {len(rows)} cached, {len(missing)} to fetch", file=sys.stderr)

    if missing:
        client = Client(*load_credentials())
        guard_cost(client, len(missing), args.max_cost)

        # 1 call: Labs keyword_overview — volume + difficulty + intent together.
        task = client.call("dataforseo_labs/google/keyword_overview/live", [{
            "keywords": missing,
            "location_code": args.location_code,
            "language_code": args.language,
        }])
        got = {}
        for item in ((task.get("result") or [{}])[0].get("items") or []):
            got[item["keyword"].lower()] = row_from_overview(item)

        # Fallback (1 call): Google Ads search_volume for keywords Labs doesn't know —
        # long-tail terms often have real volume that the Labs database misses.
        unknown = [kw for kw in missing
                   if kw.lower() not in got or got[kw.lower()].get("volume") is None]
        if unknown and client.spent < args.max_cost:
            try:
                task = client.call("keywords_data/google_ads/search_volume/live", [{
                    "keywords": unknown,
                    "location_code": args.location_code,
                    "language_code": args.language,
                }])
                for item in (task.get("result") or []):
                    kw = (item.get("keyword") or "").lower()
                    if not kw:
                        continue
                    row = got.setdefault(kw, {"kd": None, "intent": None, "cpc": None,
                                              "competition": None, "volume": None})
                    if row.get("volume") is None:
                        row["volume"] = item.get("search_volume")
                        row["cpc"] = row.get("cpc") or item.get("cpc")
            except Skip as e:  # fallback is best-effort; overview data alone is fine
                print(f"note: search_volume fallback skipped: {e}", file=sys.stderr)

        for kw in missing:
            row = got.get(kw.lower()) or {"volume": None, "kd": None, "intent": None,
                                          "cpc": None, "competition": None}
            row["checked_at"] = now_iso()
            rows[kw] = row
            cache[cache_key(kw, args.location_code, args.language)] = row
        save_cache(cpath, cache)
        print(f"spent ${client.spent:.4f} · cache → {cpath}", file=sys.stderr)

    print_table(rows, args.min_volume)
    emit(args, {
        "skipped": False,
        "min_volume": args.min_volume,
        "location_code": args.location_code,
        "language": args.language,
        "keywords": {kw: {**r, "verdict": verdict(r, args.min_volume)} for kw, r in rows.items()},
    })
    return 0


def cmd_ideas(args) -> int:
    seeds = [s.strip() for s in args.seed.split(",") if s.strip()]
    if not seeds:
        raise Skip("no seeds given (--seed)")
    client = Client(*load_credentials())
    guard_cost(client, args.limit * len(seeds), args.max_cost)
    cpath = cache_path(args)
    cache = load_cache(cpath)
    rows: dict[str, dict] = {}
    for seed in seeds:
        if client.spent >= args.max_cost:
            print(f"⚠️  --max-cost ${args.max_cost:.2f} reached, stopping before seed '{seed}'",
                  file=sys.stderr)
            break
        task = client.call("dataforseo_labs/google/keyword_suggestions/live", [{
            "keyword": seed,
            "location_code": args.location_code,
            "language_code": args.language,
            "limit": args.limit,
            "include_seed_keyword": True,
        }])
        for item in ((task.get("result") or [{}])[0].get("items") or []):
            row = row_from_overview(item)
            row["checked_at"] = now_iso()
            row["seed"] = seed
            rows[item["keyword"]] = row
            cache[cache_key(item["keyword"], args.location_code, args.language)] = row
    save_cache(cpath, cache)
    print(f"spent ${client.spent:.4f} · {len(rows)} ideas · cache → {cpath}", file=sys.stderr)
    print_table(rows, args.min_volume)
    emit(args, {
        "skipped": False,
        "seeds": seeds,
        "keywords": {kw: {**r, "verdict": verdict(r, args.min_volume)} for kw, r in rows.items()},
    })
    return 0


# --------------------------------------------------------------------- main

def add_common(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--config", help="autoblog.config.json — cache defaults next to its ledger")
    ap.add_argument("--cache", help="explicit cache file (overrides --config/global default)")
    ap.add_argument("--cache-ttl-days", type=int, default=CACHE_TTL_DAYS)
    ap.add_argument("--location-code", type=int, default=DEFAULT_LOCATION)
    ap.add_argument("--language", default=DEFAULT_LANGUAGE)
    ap.add_argument("--min-volume", type=int, default=50)
    ap.add_argument("--max-cost", type=float, default=0.50, help="max $ this run may spend")
    ap.add_argument("--out", help="write JSON result here instead of stdout")
    ap.add_argument("--strict", action="store_true", help="exit 1 on skip instead of 0")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("check", help="auth + balance (free)")
    p.add_argument("--strict", action="store_true")

    p = sub.add_parser("vet", help="volume/difficulty/intent for a candidate list")
    p.add_argument("--keywords", help="comma-separated keywords")
    p.add_argument("--keywords-file", help="file, one keyword per line (# comments ok)")
    add_common(p)

    p = sub.add_parser("ideas", help="expand seed keywords into ranked candidates")
    p.add_argument("--seed", required=True, help="comma-separated seed keywords")
    p.add_argument("--limit", type=int, default=100, help="ideas per seed")
    add_common(p)

    args = ap.parse_args()
    try:
        return {"check": cmd_check, "vet": cmd_vet, "ideas": cmd_ideas}[args.cmd](args)
    except Skip as e:
        print(f"\n⚠️  KEYWORDS {args.cmd.upper()} SKIPPED: {e}", file=sys.stderr)
        if getattr(args, "out", None):
            Path(args.out).write_text(json.dumps({"skipped": True, "reason": str(e)}) + "\n")
        print(json.dumps({"skipped": True, "reason": str(e)}))
        return 1 if args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
