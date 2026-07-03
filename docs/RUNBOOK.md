# Runbook — operations + failure modes

The system is designed so that **silence means healthy**. You get signal three ways:
GitHub workflow-failure emails, the watchdog issue ("blog queue runs dry on <date>"),
and red PRs that don't merge. Everything below is keyed to one of those signals.

## Failure modes

| Signal | What it is | Response |
|---|---|---|
| Refill run ends with "session limit / usage limit" in the Claude step log | Subscription usage window exhausted mid-batch | Do nothing — the branch keeps completed posts; the next weekly cron resumes idempotently (writes only missing files). To finish sooner, re-dispatch after the reset time. **Never lower the model to squeeze under the limit** — proven source of factual errors. |
| Watchdog issue opens | Runway < `minRunwayDays`: refill has been failing or skipping for weeks | Read the last refill run's log. Common: expired OAuth token (below), gates rejecting every batch (fix config or gates), cron disabled (below). Dispatch refill with `force: true` after fixing. |
| Refill fails immediately at the Claude step with auth error | `CLAUDE_CODE_OAUTH_TOKEN` expired or revoked | Run `claude setup-token` locally, replace the repo secret, re-dispatch. |
| No workflows have run for weeks, no emails | GitHub disables cron on repos with no activity for 60 days | Push any commit or re-enable in the Actions tab. Normally can't happen — refill merges keep the repo active — but can after long gate-failure streaks. |
| Gates red on `validate.py` | A post violates frontmatter/CTA/word-count/banned-phrase/forward-link rules | If the post is wrong, let the next refill fix it (or fix by hand). If the *rule* is wrong, fix `autoblog.config.json` — never weaken the engine for one site. |
| Gates red on `dupcheck.py` | New post overlaps an existing one beyond threshold | Usually real near-duplication → replace the topic. If a false positive (e.g. legitimately shared boilerplate), raise `quality.dupContainmentThreshold` slightly and note why in the PR. |
| Gates red on build/linkcheck | Site build broke or a rendered link 404s | This gate protects the whole site, not just the batch — fix before merging anything. |
| `hero.py --verify` red | Post publishing within 14 days lacks an image | Run refill P5 logic locally: `python3 scripts/hero.py generate --config autoblog.config.json`, commit. |
| Audit workflow always skips | No `GSC_CREDENTIALS` secret | Expected. Add a Search Console service account (JSON key, property access) to enable it. |
| Posts merged but not appearing on the live site | Daily publish layer broken (deploy hook, cron) | Check the site's publish workflow (pilot: `trigger-cloudflare-daily.yml`) and the Cloudflare deploy hook secret. The queue is intact — nothing is lost. |
| Live check confusion: unknown URLs return 200 | Some sites serve soft-404s (200 + homepage) | Verify by checking the returned `<title>`, not the HTTP status. |

## Routine operations

- **Change cadence / thresholds / voice**: edit `autoblog.config.json` in the site
  repo. The engine reads it fresh every run.
- **Flip to full autopilot**: `"autonomy": { "merge": "auto" }` after 2–3 clean
  human-reviewed batches.
- **Pause the system**: disable the three `autoblog-*` workflows in the site repo's
  Actions tab. The queue keeps publishing what's already merged.
- **Improve the machine**: fix prompts/scripts/workflows HERE (engine repo), never
  as one-off patches in a site repo. Site repos pin `@v1`; move the tag when a change
  is verified: `git tag -f v1 && git push -f origin v1`. Breaking changes → `v2` +
  update callers deliberately.
- **Upgrade hero images**: the deterministic templates are the guaranteed floor.
  AI-generated replacements can be dropped in locally any time — same path, same
  filename; gates only check existence.

## Design invariants (do not violate)

1. AI never sits in the publish path.
2. Gates are deterministic — no LLM calls in `gates.yml`.
3. Fact-checkers report; the orchestrator fixes.
4. Unresolved factual doubt → replace the topic, never ship.
5. Quality over volume: cadence caps are a Google scaled-content-abuse defense,
   not a throughput limit to optimize away.
