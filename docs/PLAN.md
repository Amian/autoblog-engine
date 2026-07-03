# Project plan — autoblog-engine

_Last updated: 2026-07-03. This is the living plan; ARCHITECTURE.md holds the design,
this file holds the why, the decisions, and the rollout state._

## Why this exists

A portfolio of subscription mobile apps, each with a marketing website, needs a
**bullet-proof, set-once-forget-forever blog system** that keeps producing
highest-quality, SEO-effective posts to drive organic + AI-search traffic → app
installs. It must be **generic** — not tied to any subject, app, or stack — so any
current or future site adopts it with one config file.

A proven single-site instance existed first: the `blog-batch` Claude skill,
battle-tested on a 60-post batch for identifyantiques.app (June 2026). This engine
generalizes that machine. Its hardest-won lessons are baked in:

- **Best-model policy**: writers and fact-checkers run on the most capable model
  available; never downgrade mid-batch. In the June 2026 batch, all 19 factual errors
  caught in review came from posts written on a smaller model.
- **Fact-checkers report, the orchestrator fixes** — a wrong "fix" is worse than a
  miss; two pairs of eyes on every finding.
- **A post with unresolved factual doubt gets replaced, not shipped.**
- **Idempotent everything** — agents die mid-batch (usage limits); every phase can
  resume by writing only what's missing.

## Decisions (locked)

1. **Standalone public repo** (`Amian/autoblog-engine`). Public because it contains
   only generic method/code — every brand voice, topic seed, and secret lives in the
   (private) site repos — and because public reusable workflows + checkouts need no PAT.
2. **Claude auth in CI**: subscription OAuth token (`claude setup-token` →
   `CLAUDE_CODE_OAUTH_TOKEN` secret per site repo), used by `anthropics/claude-code-action`.
3. **Training wheels**: refill PRs are human-reviewed at first; per-site config flag
   `autonomy.merge: "auto"` later enables auto-merge-when-gates-pass.
4. **Pilot**: the live Jekyll antiques site (`Amian/antique-website`,
   identifyantiques.app) — it already has the daily-publish layer
   (`trigger-cloudflare-daily.yml`, 4×/day Cloudflare rebuild, `future: false`).

## Architecture in one paragraph

Posts are committed to the site repo with future dates (the **queue**). A scheduled
rebuild publishes whatever is due (**daily publish**, no AI). A weekly **refill**
workflow measures queue runway and exits free if healthy; when low, Claude researches
topics against a persistent **topic ledger**, writes posts (parallel best-model
writers), fact-checks with web-grounded checkers, generates deterministic hero images,
and opens a PR. **Gates** (pure scripts) validate frontmatter, links, duplicates,
banned phrases, and the site build. A daily **watchdog** opens an issue if runway drops
below 7 days; a monthly **audit** feeds Search Console data back into the ledger.
Full detail: [ARCHITECTURE.md](ARCHITECTURE.md).

## Rollout phases

- [x] **Phase 0 — repo + docs**: this repo, on GitHub, public.
- [x] **Phase 1 — scripts**: `runway / validate / dupcheck / linkcheck / hero / ledger`,
      tested locally against the real antiques corpus (130 posts; runway reported
      dry date 2026-08-10 correctly; validate `--scope future` 0 errors, dupcheck max
      overlap 0.047, linkcheck 645 pages 0 broken — false positives calibrated).
- [x] **Phase 2 — prompts + workflows**: `prompts/*`, 5 reusable workflows, caller
      templates, config JSON Schema. Tagged `v1`.
- [ ] **Phase 3 — pilot onboarding**: config + seeded ledger + 3 caller workflows in
      the antiques repo; user adds the token secret; gates green on a no-op PR;
      dry-run refill green via `workflow_dispatch`.
- [ ] **Phase 4 — first real batch**: refill with `force: true` → PR → gates green →
      human review/merge → posts publish on the existing rebuild → verify live URLs.
- [ ] **Phase 5 — later**: `astro-content` adapter + monorepo site enablement
      (needs that site deployed first); flip `autonomy.merge: "auto"` after 2–3 clean
      batches; optional GSC service account for the audit workflow.

## Standing risks (mitigations in RUNBOOK.md)

- Subscription usage limits mid-batch → small weekly top-ups, idempotent resume,
  cron retries, optional API-key fallback.
- GitHub cron drift / 60-day auto-disable on inactive repos → refill commits keep
  repos active; failure emails surface silent stops.
- Google scaled-content-abuse policy → cadence caps, information-gain requirement
  per topic, fact-check gate, honest sourcing. Quality over volume, always.
