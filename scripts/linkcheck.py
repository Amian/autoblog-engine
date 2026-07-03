#!/usr/bin/env python3
"""Full-depth internal link check over a built site.

  python3 linkcheck.py --dist tmp/_site_future [--ignore /admin/ --ignore /draft/]

Walks every rendered .html file (all depths — tag/category pages included),
extracts root-relative href/src targets, and verifies each resolves to a file
in the dist dir (path, path/index.html, or path.html). External, mailto:,
tel:, data: and protocol-relative URLs are skipped. Exit 1 on broken links.
"""
from __future__ import annotations

import argparse
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote


class LinkExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name in ("href", "src") and value:
                self.links.append(value)


def resolves(dist: Path, target: str) -> bool:
    rel = unquote(target).lstrip("/")
    if rel == "":
        return (dist / "index.html").is_file()
    p = dist / rel
    if target.endswith("/"):
        return (p / "index.html").is_file() or p.is_file()
    return p.is_file() or (p / "index.html").is_file() or p.with_suffix(p.suffix + ".html").is_file() \
        if p.suffix else p.is_file() or (p / "index.html").is_file() or Path(str(p) + ".html").is_file()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dist", required=True)
    ap.add_argument("--ignore", action="append", default=[],
                    help="path prefix to skip (repeatable)")
    args = ap.parse_args()
    dist = Path(args.dist)
    if not dist.is_dir():
        print(f"ERROR: dist dir not found: {dist}", file=sys.stderr)
        return 2

    broken: dict[str, list[str]] = {}
    pages = 0
    checked: dict[str, bool] = {}
    for page in dist.rglob("*.html"):
        pages += 1
        extractor = LinkExtractor()
        try:
            extractor.feed(page.read_text(encoding="utf-8", errors="replace"))
        except Exception as e:  # malformed HTML shouldn't kill the gate
            print(f"warn  unparseable HTML {page}: {e}")
            continue
        for raw in extractor.links:
            target = raw.split("#")[0].split("?")[0]
            if not target.startswith("/") or target.startswith("//"):
                continue
            if any(target.startswith(pfx) for pfx in args.ignore):
                continue
            if target not in checked:
                checked[target] = resolves(dist, target)
            if not checked[target]:
                broken.setdefault(target, []).append(str(page.relative_to(dist)))

    for target, sources in sorted(broken.items()):
        srcs = ", ".join(sources[:3]) + (f" (+{len(sources) - 3} more)" if len(sources) > 3 else "")
        print(f"ERROR broken link {target}  ← {srcs}")
    print(f"\nchecked {pages} pages, {len(checked)} unique internal targets: {len(broken)} broken")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
