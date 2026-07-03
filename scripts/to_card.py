#!/usr/bin/env python3
"""Convert a source image into a post's hero card at the site's standard size.

  python3 to_card.py --config autoblog.config.json --slug <slug> --src path/to/image.png [--repo .]

Center-crops the source to the config `images.size` aspect ratio, resizes to that
size, and writes it as a JPEG to the post's frontmatter image path (the
`images.imageField` value, e.g. /images/blog/<slug>-card.jpg). Cross-platform
(Pillow), so it works locally and in CI. Used by the AI-image pipeline after a
generated image passes review; the deterministic hero.py is the fallback when no
acceptable AI image exists.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import iter_posts, load_config


def post_image_path(cfg: dict, repo: Path, slug: str) -> Path:
    field = cfg["content"]["frontmatter"]["imageField"]
    for p in iter_posts(cfg, repo):
        if p.slug == slug:
            val = str(p.fm.get(field, ""))
            if not val.startswith("/"):
                sys.exit(f"post {slug} has no usable {field!r} frontmatter path: {val!r}")
            return repo / val.lstrip("/")
    sys.exit(f"no post with slug {slug!r} in {cfg['content']['dir']}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--slug", required=True)
    ap.add_argument("--src", required=True)
    ap.add_argument("--repo", default=".")
    args = ap.parse_args()

    from PIL import Image
    cfg = load_config(args.config)
    repo = Path(args.repo)
    w, h = cfg["images"]["size"]
    src = Path(args.src)
    if not src.is_file():
        sys.exit(f"source image not found: {src}")

    img = Image.open(src).convert("RGB")
    sw, sh = img.size
    target = w / h
    # center-crop to target aspect, then resize
    if sw / sh > target:
        new_w = int(sh * target)
        left = (sw - new_w) // 2
        img = img.crop((left, 0, left + new_w, sh))
    else:
        new_h = int(sw / target)
        top = (sh - new_h) // 2
        img = img.crop((0, top, sw, top + new_h))
    img = img.resize((w, h), Image.LANCZOS)

    out = post_image_path(cfg, repo, args.slug)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, quality=88)
    print(f"wrote {out.relative_to(repo)} ({w}x{h}) from {src.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
