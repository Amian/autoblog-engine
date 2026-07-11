#!/usr/bin/env python3
"""Config-driven post validation — the core quality gate.

  python3 validate.py --config autoblog.config.json [--repo .] [--scope all|future]

Checks per post:
  - filename matches content.filenamePattern; date/slug agree with frontmatter
  - required frontmatter fields present and non-empty; constant fields match
  - description within frontmatter.descriptionMaxChars
  - CTA snippet present (error) and is the final content line (warning)
  - body word count >= editorial.wordCount.min
  - no banned phrases (case-insensitive, body text)
  - cluster value exists in content.clustersFile (when configured)
  - internal post links (matching content.urlPattern) resolve to a known post
    that publishes on or before this post's date  ← "never link forward in time"
Corpus-wide:
  - at most cadence.postsPerDayMax posts per date
  - at most cadence.postsPerWeek posts per ISO week (future posts only)
  - unique slugs

Exit 0 = clean (warnings allowed), 1 = errors found, 2 = config/setup problem.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import Post, iter_posts, load_clusters, load_config, parse_date, today, url_pattern_regex

MD_LINK_RE = re.compile(r"\]\((/[^)\s]+)\)")


def body_word_count(body: str) -> int:
    text = re.sub(r"\{%.*?%\}", " ", body)          # liquid tags
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)  # images
    text = re.sub(r"\]\([^)]*\)", "]", text)          # link targets
    text = re.sub(r"[#>*`|_-]+", " ", text)
    return len(text.split())


def validate_post(post: Post, cfg: dict, clusters: set | None,
                  post_dates: dict, url_re: re.Pattern) -> tuple[list, list]:
    errors: list[str] = list(post.problems)
    warnings: list[str] = []
    fmcfg = cfg["content"]["frontmatter"]
    fm, body = post.fm, post.body

    for field in fmcfg["required"]:
        v = fm.get(field)
        if v is None or v == "" or v == []:
            errors.append(f"missing/empty required frontmatter field: {field}")
    for field, expected in fmcfg["constant"].items():
        if field in fm and fm[field] != expected:
            errors.append(f"frontmatter {field}={fm[field]!r}, must be {expected!r}")

    fm_slug = str(fm.get("slug", "")) if "slug" in fm else post.slug
    if fm_slug and post.slug and fm_slug != post.slug:
        errors.append(f"slug mismatch: filename {post.slug!r} vs frontmatter {fm_slug!r}")
    fm_date = fm.get(fmcfg["dateField"])
    if fm_date is not None:
        try:
            if parse_date(fm_date) != post.date:
                errors.append(f"date mismatch: filename {post.date} vs frontmatter {fm_date!r}")
        except ValueError:
            errors.append(f"unparseable frontmatter date: {fm_date!r}")

    desc = str(fm.get("description", ""))
    if desc and not (fmcfg["descriptionMinChars"] <= len(desc) <= fmcfg["descriptionMaxChars"]):
        errors.append(f"description {len(desc)} chars (want {fmcfg['descriptionMinChars']}-{fmcfg['descriptionMaxChars']})")

    cta = cfg["content"]["ctaSnippet"]
    if cta:
        if cta not in body:
            errors.append("CTA snippet missing (file incomplete?)")
        elif not body.rstrip().endswith(cta):
            warnings.append("CTA snippet is not the final content line")

    wc = body_word_count(body)
    if wc < cfg["editorial"]["wordCount"]["min"]:
        errors.append(f"body {wc} words (min {cfg['editorial']['wordCount']['min']})")

    lower = body.lower()
    for phrase in cfg["editorial"]["bannedPhrases"]:
        if phrase.lower() in lower:
            errors.append(f"banned phrase present: {phrase!r}")

    cluster_field = fmcfg["clusterField"]
    if clusters is not None and cluster_field in fm:
        if str(fm[cluster_field]) not in clusters:
            errors.append(f"unknown cluster: {fm[cluster_field]!r}")

    # Forward-link rule: a queue post linking to a later-dated post would be
    # broken on its own publish day → error. A published post linking to a
    # still-future post is the deliberate reverse-link pattern → warning only.
    now = today()
    for target in MD_LINK_RE.findall(body):
        path = target.split("#")[0].split("?")[0]
        m = url_re.match(path)
        if not m:
            continue  # not a post URL; linkcheck.py covers it post-build
        slug = m.group("slug")
        if slug not in post_dates:
            errors.append(f"links to unknown post: {path}")
        elif post.date > now and post_dates[slug] > post.date:
            errors.append(f"links to post published later: {path} ({post_dates[slug]})")
        elif post.date <= now < post_dates[slug]:
            warnings.append(f"reverse-link to still-future post: {path} ({post_dates[slug]})")

    return errors, warnings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--repo", default=".")
    ap.add_argument("--scope", choices=["all", "future"], default="all",
                    help="future = only posts dated after today (plus corpus-wide checks)")
    args = ap.parse_args()

    cfg = load_config(args.config)
    repo = Path(args.repo)
    posts = iter_posts(cfg, repo)
    clusters = load_clusters(cfg, repo)
    url_re = url_pattern_regex(cfg)
    post_dates = {p.slug: p.date for p in posts if p.slug}

    now = today()
    targets = posts if args.scope == "all" else [p for p in posts if p.date > now]

    total_errors = 0
    total_warnings = 0
    for post in targets:
        errors, warnings = validate_post(post, cfg, clusters, post_dates, url_re)
        for e in errors:
            print(f"ERROR {post.path.name}: {e}")
        for w in warnings:
            print(f"warn  {post.path.name}: {w}")
        total_errors += len(errors)
        total_warnings += len(warnings)

    # corpus-wide checks always run on everything
    by_date: dict = {}
    for p in posts:
        by_date.setdefault(p.date, []).append(p.path.name)
    cap = cfg["cadence"]["postsPerDayMax"]
    for d, names in sorted(by_date.items()):
        # the day cap is queue discipline — history is grandfathered
        if d > now and len(names) > cap:
            print(f"ERROR {d}: {len(names)} posts on one day (max {cap}): {', '.join(names)}")
            total_errors += 1
    week_cap = cfg["cadence"]["postsPerWeek"]
    by_week: dict = {}
    for p in posts:
        if p.date > now:
            by_week.setdefault(p.date.isocalendar()[:2], []).append(p.path.name)
    for wk, names in sorted(by_week.items()):
        # the week cap is queue discipline too — history is grandfathered
        if len(names) > week_cap:
            print(f"ERROR week {wk[0]}-W{wk[1]:02d}: {len(names)} posts in one week "
                  f"(max {week_cap}): {', '.join(sorted(names))}")
            total_errors += 1
    seen: dict = {}
    for p in posts:
        if p.slug and p.slug in seen:
            print(f"ERROR duplicate slug {p.slug!r}: {seen[p.slug]} and {p.path.name}")
            total_errors += 1
        seen[p.slug] = p.path.name

    print(f"\nchecked {len(targets)} posts ({len(posts)} in corpus): "
          f"{total_errors} errors, {total_warnings} warnings")
    return 1 if total_errors else 0


if __name__ == "__main__":
    sys.exit(main())
