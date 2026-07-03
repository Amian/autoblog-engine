"""Shared helpers for autoblog-engine scripts.

Stdlib only. Frontmatter parsing supports the YAML subset these blogs actually
use: scalar strings (quoted or bare), numbers, booleans, null, inline empty
lists, and block lists of scalars. Anything fancier should not be in post
frontmatter in the first place.
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

DEFAULTS = {
    "content": {
        "filenamePattern": "{date}-{slug}.md",
        "urlPattern": "/blog/{slug}/",
        "frontmatter": {
            "required": ["title", "date", "slug", "description"],
            "constant": {},
            "dateField": "date",
            "clusterField": "cluster",
            "imageField": "image",
            "descriptionMinChars": 0,
            "descriptionMaxChars": 160,
        },
        "ctaSnippet": "",
        "clustersFile": "",
    },
    "editorial": {
        "commercialPostsPerWeek": 1,
        "seasonalLeadWeeks": [6, 10],
        "wordCount": {"min": 1200, "target": 1800},
        "bannedPhrases": [],
        "hardRules": [],
    },
    "cadence": {"postsPerDayMax": 1, "batchTargetDays": 21, "refillThresholdDays": 21},
    "quality": {"minRunwayDays": 7, "dupContainmentThreshold": 0.5, "factCheck": True},
    "images": {
        "mode": "template",
        "brandColors": ["#1f2937", "#b45309"],
        "textColor": "#f8f5ee",
        "size": [1200, 630],
        "fontPath": "",
        "verifyWithinDays": 14,
        "ai": {
            "enabled": False,
            "style": "",
            "negative": [],
            "reviewMaxAttempts": 3,
        },
    },
    "build": {"rubyVersion": "3.3", "nodeVersion": "22"},
    "autonomy": {"merge": "review"},
    "models": {"writer": "best", "checker": "best"},
    "audit": {"gsc": "auto"},
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: str | Path) -> dict:
    p = Path(path)
    if not p.is_file():
        die(f"config not found: {p}")
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"config is not valid JSON: {p}: {e}")
    if raw.get("version") != 1:
        die(f"config version must be 1, got {raw.get('version')!r}")
    for key in ("site", "adapter", "content", "build"):
        if key not in raw:
            die(f"config missing required section: {key}")
    return _deep_merge(DEFAULTS, raw)


def die(msg: str) -> "None":
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(2)


# ---------------------------------------------------------------- frontmatter

_FM_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)


def _parse_scalar(raw: str):
    s = raw.strip()
    if s == "" or s == "~" or s == "null":
        return None
    if s == "[]":
        return []
    if s == "{}":
        return {}
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        body = s[1:-1]
        if s[0] == '"':
            body = body.replace('\\"', '"').replace("\\\\", "\\")
        return body
    if s in ("true", "True"):
        return True
    if s in ("false", "False"):
        return False
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter dict, body). Raises ValueError if no frontmatter block."""
    m = _FM_RE.match(text)
    if not m:
        raise ValueError("no frontmatter block")
    block, body = m.group(1), m.group(2)
    fm: dict = {}
    current_list_key = None
    for line in block.split("\n"):
        if not line.strip() or line.strip().startswith("#"):
            continue
        item = re.match(r"\s+-\s*(.*)$", line)
        if item and current_list_key is not None:
            fm[current_list_key].append(_parse_scalar(item.group(1)))
            continue
        kv = re.match(r"([A-Za-z0-9_-]+):\s*(.*)$", line)
        if kv:
            key, raw = kv.group(1), kv.group(2)
            if raw.strip() == "":
                fm[key] = []
                current_list_key = key
            else:
                fm[key] = _parse_scalar(raw)
                current_list_key = None
            continue
        raise ValueError(f"unparseable frontmatter line: {line!r}")
    return fm, body


# ---------------------------------------------------------------------- posts

@dataclass
class Post:
    path: Path
    slug: str
    date: date
    fm: dict
    body: str
    problems: list = field(default_factory=list)


def _pattern_to_regex(pattern: str) -> re.Pattern:
    esc = re.escape(pattern)
    esc = esc.replace(re.escape("{date}"), r"(?P<date>\d{4}-\d{2}-\d{2})")
    esc = esc.replace(re.escape("{slug}"), r"(?P<slug>[a-z0-9][a-z0-9-]*)")
    return re.compile(r"\A" + esc + r"\Z")


def parse_date(value) -> date:
    if isinstance(value, date):
        return value
    s = str(value).strip()
    return datetime.strptime(s[:10], "%Y-%m-%d").date()


def iter_posts(cfg: dict, repo: Path) -> list[Post]:
    """Load every post in content.dir. Files that fail to parse become Posts with
    problems recorded (so validators can report instead of crashing)."""
    content = cfg["content"]
    cdir = repo / content["dir"]
    if not cdir.is_dir():
        die(f"content dir not found: {cdir}")
    fname_re = _pattern_to_regex(content["filenamePattern"])
    date_field = content["frontmatter"]["dateField"]
    posts: list[Post] = []
    for path in sorted(cdir.iterdir()):
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.suffix not in (".md", ".mdx", ".markdown"):
            continue
        m = fname_re.match(path.name)
        problems = []
        if not m:
            problems.append(f"filename does not match pattern {content['filenamePattern']!r}")
        try:
            fm, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        except ValueError as e:
            posts.append(Post(path, "", date.min, {}, "", [f"frontmatter: {e}"]))
            continue
        slug = (m.group("slug") if m and "slug" in fname_re.groupindex else None) or str(fm.get("slug", ""))
        raw_date = (m.group("date") if m and "date" in fname_re.groupindex else None) or fm.get(date_field)
        try:
            pdate = parse_date(raw_date)
        except (ValueError, TypeError):
            problems.append(f"unparseable date {raw_date!r}")
            pdate = date.min
        posts.append(Post(path, slug, pdate, fm, body, problems))
    return posts


def today() -> date:
    return datetime.now(timezone.utc).date()


def url_for(cfg: dict, slug: str) -> str:
    return cfg["content"]["urlPattern"].replace("{slug}", slug)


def url_pattern_regex(cfg: dict) -> re.Pattern:
    esc = re.escape(cfg["content"]["urlPattern"])
    esc = esc.replace(re.escape("{slug}"), r"(?P<slug>[a-z0-9][a-z0-9-]*)")
    return re.compile(r"\A" + esc + r"\Z")


def load_clusters(cfg: dict, repo: Path) -> set[str] | None:
    """Return valid cluster slugs, or None if unconfigured/unparseable."""
    rel = cfg["content"].get("clustersFile")
    if not rel:
        return None
    p = repo / rel
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    clusters = data.get("clusters")
    return set(clusters.keys()) if isinstance(clusters, dict) else None


def github_output(**kwargs) -> None:
    """Append key=value pairs to $GITHUB_OUTPUT when running in Actions."""
    out = os.environ.get("GITHUB_OUTPUT")
    if not out:
        return
    with open(out, "a", encoding="utf-8") as f:
        for k, v in kwargs.items():
            f.write(f"{k}={v}\n")
