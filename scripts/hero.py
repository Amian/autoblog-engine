#!/usr/bin/env python3
"""Deterministic branded hero images — the guaranteed floor, never blocks.

  python3 hero.py generate --config autoblog.config.json [--repo .] [--force] [--slug SLUG]
  python3 hero.py verify   --config autoblog.config.json [--repo .]

`generate` renders a card for every post whose frontmatter image file is
missing (Pillow; brand colors, wrapped title, per-slug accent geometry).
`verify` (the gate) fails if any post publishing within images.verifyWithinDays
lacks its image file. AI-generated replacements can overwrite these any time —
same path, same filename.
"""
from __future__ import annotations

import argparse
import sys
import zlib
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import iter_posts, load_config, today, image_repo_path

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",          # ubuntu CI
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",             # macOS
    "/System/Library/Fonts/Helvetica.ttc",
]


def hex_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mix(a: tuple, b: tuple, t: float) -> tuple:
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def load_font(cfg, size):
    from PIL import ImageFont
    paths = ([cfg["images"]["fontPath"]] if cfg["images"]["fontPath"] else []) + FONT_CANDIDATES
    for p in paths:
        if Path(p).is_file():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default(size)


def wrap_title(draw, title, font, max_width):
    lines, line = [], ""
    for word in title.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def render(cfg: dict, title: str, slug: str, cluster: str, out: Path) -> None:
    from PIL import Image, ImageDraw
    w, h = cfg["images"]["size"]
    bg = hex_rgb(cfg["images"]["brandColors"][0])
    accent = hex_rgb(cfg["images"]["brandColors"][1] if len(cfg["images"]["brandColors"]) > 1
                     else cfg["images"]["brandColors"][0])
    fg = hex_rgb(cfg["images"]["textColor"])
    img = Image.new("RGB", (w, h), bg)
    draw = ImageDraw.Draw(img)

    # deterministic per-slug accent geometry: one large soft disc off-canvas
    seed = zlib.crc32(slug.encode())
    cx = w - 60 - (seed % 240)
    cy = (seed >> 8) % h
    r = h // 2 + (seed >> 16) % (h // 3)
    disc = mix(bg, accent, 0.35)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=disc)
    ring = mix(bg, accent, 0.55)
    rr = r + 26
    draw.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=ring, width=3)

    margin = 72
    brand_font = load_font(cfg, 30)
    site = cfg["site"]["name"].upper()
    draw.text((margin, margin - 8), site, font=brand_font, fill=mix(bg, fg, 0.75))
    bar_w = int(draw.textlength(site, font=brand_font))
    draw.rectangle([margin, margin + 34, margin + bar_w, margin + 38], fill=accent)

    size = 76
    while size >= 40:
        title_font = load_font(cfg, size)
        lines = wrap_title(draw, title, title_font, w - 2 * margin - 120)
        line_h = size + 14
        if len(lines) * line_h <= h - 300:
            break
        size -= 8
    y = (h - len(lines) * line_h) // 2 + 20
    for line in lines:
        draw.text((margin, y), line, font=title_font, fill=fg)
        y += line_h

    if cluster:
        tag_font = load_font(cfg, 26)
        label = cluster.replace("-", " ")
        draw.text((margin, h - margin - 22), label, font=tag_font, fill=mix(bg, accent, 0.85))

    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix.lower() in (".jpg", ".jpeg"):
        img.save(out, quality=88)
    else:
        img.save(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["generate", "verify"])
    ap.add_argument("--config", required=True)
    ap.add_argument("--repo", default=".")
    ap.add_argument("--force", action="store_true", help="regenerate even if the file exists")
    ap.add_argument("--slug", default=None, help="only this post")
    args = ap.parse_args()

    cfg = load_config(args.config)
    if cfg["images"]["mode"] == "off":
        print("images.mode = off — nothing to do")
        return 0
    repo = Path(args.repo)
    image_field = cfg["content"]["frontmatter"]["imageField"]
    cluster_field = cfg["content"]["frontmatter"]["clusterField"]
    posts = [p for p in iter_posts(cfg, repo) if p.slug and (not args.slug or p.slug == args.slug)]

    if args.command == "verify":
        horizon = today() + timedelta(days=cfg["images"]["verifyWithinDays"])
        missing = 0
        for p in posts:
            if p.date > horizon:
                continue
            path = image_repo_path(cfg, repo, p.fm.get(image_field, ""))
            if path is None:
                print(f"ERROR {p.path.name}: no usable {image_field!r} frontmatter value")
                missing += 1
            elif not path.is_file():
                print(f"ERROR {p.path.name}: image missing: {p.fm.get(image_field)}")
                missing += 1
        print(f"verified images for posts through {horizon}: {missing} missing")
        return 1 if missing else 0

    made = skipped = 0
    for p in posts:
        path = image_repo_path(cfg, repo, p.fm.get(image_field, ""))
        if path is None:
            print(f"warn  {p.path.name}: no usable {image_field!r} value, skipping")
            continue
        if path.is_file() and not args.force:
            skipped += 1
            continue
        render(cfg, str(p.fm.get("title", p.slug)), p.slug,
               str(p.fm.get(cluster_field, "")), path)
        print(f"generated {path.relative_to(repo)}")
        made += 1
    print(f"generated {made}, already present {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
