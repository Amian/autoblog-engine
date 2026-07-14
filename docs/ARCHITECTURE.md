# Architecture

```
topic ledger + GSC data ──▶ weekly refill (Claude, GH Actions) ──▶ PR ──▶ CI gates (no AI)
                                                                            │ green
                                                                            ▼
                                              content queue (future-dated posts in git)
                                                                            │
                          daily publish (build + deploy, no AI) ◀───────────┘
                                          │
                                          ▼
                          live site (Cloudflare) ──▶ IndexNow / sitemap ping
                                          │
                       monthly audit (GSC → refresh, prune, retarget ledger)
                       daily watchdog (issue if queue runway < 7 days)
```

**The load-bearing idea: AI never sits in the publish path.** Publication is a
deterministic scheduled rebuild of whatever is due. Generation happens in batches,
ahead of time, behind gates, into a buffer. A generation failure is therefore
*invisible* — the queue keeps draining while you fix it on your own schedule.

## Components

### 1. Content queue
Future-dated posts committed to the site repo (e.g. Jekyll `_posts/` with
`future: false`, or an Astro content collection filtered by `pubDate <= now`).
Git is the database: versioned, diffable, reviewable, nothing to host.

### 2. Daily publish (deterministic)
A scheduled job rebuilds and deploys the site; posts whose date has arrived appear.
Sites bring their own (the pilot's 4×/day Cloudflare deploy-hook trigger) or use the
engine's reusable `publish.yml` (build → deploy hook → IndexNow ping for URLs due today).

### 3. Weekly refill (the only place AI runs)
Reusable workflow `refill.yml`, two jobs:

1. **runway** — `scripts/runway.py` computes days of queue left. If
   `days >= cadence.refillThresholdDays` and not forced: exit 0, zero tokens spent.
2. **generate** — `anthropics/claude-code-action` with `prompts/refill.md`. Phases:
   - **P0 Discover**: parse config; inventory every post (slug/title/cluster/date);
     read ledger + clusters file; compute the batch window.
   - **P1 Research → calendar**: apply `prompts/topic-method.md` with the site's
     archetypes. Cannibalization intent-check against the full inventory, funnel-post
     ratio, seasonal lead time, web-search SERP-gap recon for the highest-stakes
     topics (every calendar row records the information-gain angle). Related links
     may only point to posts already live or earlier in the same batch.
     `scripts/keywords.py vet` (DataForSEO, optional) prices every candidate's
     real search volume / difficulty / intent for pennies — dead topics dropped,
     slots ranked volume×ease, results cached in `autoblog/keywords-cache.json`.
     No credentials or no balance → loud SKIPPED banner, heuristic fallback,
     never blocks a refill.
   - **P2 Write**: parallel writer subagents (~5 posts each) on the best model,
     from a writer spec instantiated with the site's voice/audience/CTA. Idempotent:
     a file is complete only if it ends with the CTA snippet; resume writes only
     missing files.
   - **P3 Validate**: `scripts/validate.py`; fix; repeat until clean.
   - **P4 Fact-check**: parallel checker subagents (best model), web-search-grounded
     on each post's riskiest factual claims. Report-only — the orchestrator applies
     fixes. Unresolved doubt → topic replaced with a backup, never shipped.
   - **P5 Images**: `scripts/hero.py` — deterministic branded hero for every post.
     Never blocks; AI image upgrades are a manual local nicety.
   - **P6 Ship**: reverse-link pass (closest older cluster-sibling links back to each
     new post), ledger update + queue-dry date, commit to `autoblog/refill-<date>`,
     PR with a structured body. `autonomy.merge: "auto"` → `gh pr merge --auto`.

   `concurrency: autoblog-refill` prevents overlapping runs; timeout 5h;
   `dry_run` stops after 2 posts + the calendar and opens no PR.

### 4. Gates (deterministic, no AI)
Reusable workflow `gates.yml`, triggered by the site's PR workflow:
config schema check → `validate.py` (frontmatter required/constant fields,
filename↔date↔slug consistency, description length, CTA present, word count, banned
phrases, posts-per-day cap, unique slugs, **no link to a post published later**) →
`dupcheck.py` (shingle overlap vs the whole corpus) → site build (`build.command`) →
`linkcheck.py` over the built HTML (full depth) → `hero.py --verify` (posts publishing
within 14 days must have images). Any failure = red PR = nothing enters the queue.

### 5. Watchdog
Daily `watchdog.yml`: if runway < `quality.minRunwayDays`, open/update a pinned issue
("blog queue runs dry on <date>"); auto-close it when healthy again. GitHub's built-in
workflow-failure emails cover everything else. Silence means healthy.

### 6. Monthly audit
`audit.yml`: skips gracefully unless a `GSC_CREDENTIALS` secret exists. With it,
Claude pulls 90 days of Search Console query/page data and (a) updates the ledger with
winning clusters, (b) opens refresh PRs for posts ranking 5–15 (the quickest wins),
(c) lists zero-impression posts ≥ 6 months old as prune candidates in an issue —
never auto-deletes.

## The topic ledger (`autoblog/ledger.json` in the site repo)
The "forever" memory: every topic `covered | scheduled | rejected | candidate` with
slug, priority keyword, cluster, date. Refill reads it first; cannibalization is
checked against it AND a live scan of the content dir (the ledger can drift — files
are truth). The audit writes winners back into it. This is what makes year-three
output still coherent instead of repetitive.

## Genericity: the adapter contract
An adapter is **pure config, no code fork**. What varies per stack:

| Config field | Jekyll (pilot) | Astro content collection |
|---|---|---|
| `content.dir` | `_posts` | `src/content/blog` |
| `content.filenamePattern` | `{date}-{slug}.md` | `{slug}.md` (date in frontmatter) |
| `content.urlPattern` | `/blog/{slug}/` | `/blog/{slug}/` |
| `build.command` | `bundle exec jekyll build --future …` | `pnpm build` |
| `build.setup` | `ruby-bundler` | `node-pnpm` |
| publish mechanism | site's own cron trigger | engine `publish.yml` |

Scripts read these fields; prompts interpolate them. A new stack = a new config file,
not new engine code.

## Security / separation
- Engine repo: public, generic, zero secrets, zero brand content.
- Site repos: private; hold `autoblog.config.json` (voice, audience, topics),
  the ledger, and all secrets (`CLAUDE_CODE_OAUTH_TOKEN`, deploy hook, GSC).
- The refill agent gets `contents: write` + `pull-requests: write` on the site repo
  only; gates run with read-only permissions.
