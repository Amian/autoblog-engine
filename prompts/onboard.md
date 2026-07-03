# Onboard a site onto autoblog-engine

You are wiring a site repo into autoblog-engine. Work in the site repo; the engine
lives at `https://github.com/Amian/autoblog-engine` (clone it to a temp dir for
reference and to copy caller templates). Read `docs/CONFIG.md` and
`docs/SITE-SETUP.md` in the engine first.

## 1. Understand the site (before writing anything)

- Detect the stack (Jekyll `_config.yml` / Astro `astro.config.*` / plain md) and how
  posts are stored, named, and rendered. Confirm date-gating exists: Jekyll needs
  `future: false`; an SSG needs a build-time filter on the date field. **If future
  posts would render immediately, STOP and tell the user what to add first.**
- Confirm a scheduled publish mechanism exists (a cron workflow triggering rebuilds).
  If none, plan to include the engine's `autoblog-publish.yml` caller template.
- Read 2–3 recent posts for the exact frontmatter contract; read any clusters/backlog
  data files; find the CTA include/component that ends a post.
- Interview the repo (and the user if needed) for the editorial soul: who reads this,
  what moment converts them (the funnel), what the voice sounds like, which topic
  archetypes have endless long tails. Rich archetypes are the highest-leverage part
  of the whole config — spend real effort here.

## 2. Write the files

1. `autoblog.config.json` per `docs/CONFIG.md` — validate against
   `schema/autoblog.config.schema.json`.
2. Seed the ledger:
   `python3 <engine>/scripts/ledger.py seed --config autoblog.config.json [--backlog <file>]`
3. Copy the caller workflows from `caller-templates/` into `.github/workflows/`
   (refill, gates, watchdog; publish too if needed). Adjust cron times only if the
   user asks.

## 3. Calibrate on the real corpus (do not skip)

- `runway.py` — sanity-check days + dry date against reality.
- `validate.py --scope future` must be clean; `--scope all` failures on old posts are
  acceptable but review them — they often reveal a config field set wrong.
- `dupcheck.py --scope future` must pass; note the top overlaps.
- Build the site with `build.command`, then `linkcheck.py --dist <distDir>` — clean.
- `hero.py verify` — clean, or generate the missing images.
Fix the CONFIG (not the engine) until the real corpus is green.

## 4. Hand off to the user

Commit + push (or PR) the new files, then tell the user exactly what remains manual:
- Add `CLAUDE_CODE_OAUTH_TOKEN` secret (`claude setup-token`), plus
  `CLOUDFLARE_DEPLOY_HOOK` / `GSC_CREDENTIALS` / `AUTOBLOG_PAT` as applicable.
- Install the Claude GitHub App on the repo if not already (`claude /install-github-app`).
- Then run the verification ladder from `docs/SITE-SETUP.md` §5: gates on a no-op PR →
  watchdog dispatch → `dry_run` refill dispatch → first real batch with review.
