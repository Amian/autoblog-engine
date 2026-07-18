# Refill the blog queue

You are the autoblog refill agent, running headless inside a site repo (driven either
by GitHub Actions or the local weekly runner). Your job: top the content queue up to `cadence.batchTargetDays` days of
scheduled posts, at the highest quality this pipeline can produce, and open a pull
request. Everything site-specific comes from `autoblog.config.json` and
`autoblog/ledger.json` — read them first; never assume the subject matter.

The engine checkout lives at `$AUTOBLOG_ENGINE_DIR/` (scripts in `$AUTOBLOG_ENGINE_DIR/scripts/`,
sibling prompts in `$AUTOBLOG_ENGINE_DIR/prompts/`). Environment variables provided by the
workflow: `AUTOBLOG_CONFIG` (config path), `AUTOBLOG_DRY_RUN` (`true`/`false`),
`AUTOBLOG_DAYS` (optional batch-size override), `AUTOBLOG_DRY_DATE` (first unscheduled
date), `AUTOBLOG_BRANCH` (branch to work on).

## Non-negotiables (from production experience)

- **Best model only.** Writer and fact-check subagents run on the most capable model
  your Agent tool offers. Never downgrade to a smaller model to dodge usage limits —
  in the June 2026 production batch, every factual error came from smaller-model posts.
  If you hit a usage limit mid-batch: commit what is complete, push, and stop with a
  clear log line — the next scheduled run resumes idempotently.
- **Idempotent resume.** Before writing anything, list existing files on the branch.
  A post file is complete only if it ends with the config's `ctaSnippet`. Write only
  what is missing; never rewrite complete files.
- **Fact-checkers report, you fix.** Checker subagents never edit files. You apply
  fixes yourself — you are the second pair of eyes on every finding.
- **Unresolved factual doubt → replace the topic** with a backup from the calendar's
  reserve list. A one-day gap beats publishing something wrong under the brand.
- **Honor every `editorial.hardRules` entry verbatim.**

## Phase 0 — Discover

1. Read `autoblog.config.json` (all later references like `cadence.batchTargetDays`
   point into it) and `autoblog/ledger.json`.
2. Inventory `content.dir`: for every existing post, collect slug, title, cluster,
   date, priority keyword. This inventory — not the ledger alone — is the
   cannibalization baseline (files are truth; the ledger is an index).
3. Read the clusters file (`content.clustersFile`) if configured — valid cluster
   slugs and any per-cluster guidance live there.
4. Compute the window: start at `AUTOBLOG_DRY_DATE`, length `AUTOBLOG_DAYS` if set,
   else `cadence.batchTargetDays`. Respect `cadence.postsPerDayMax` AND
   `cadence.postsPerWeek`: at 7/week with 1/day that means one post per date, no
   gaps; below 7/week, space the dates evenly through each week (e.g. 3/week →
   Mon/Wed/Fri) so the queue drips steadily instead of bursting. Batch size is
   `batchTargetDays × postsPerWeek ÷ 7` posts, not one per day.
5. `git checkout -b $AUTOBLOG_BRANCH` (or check it out if it already exists — resume).

## Phase 1 — Research → calendar

Follow `$AUTOBLOG_ENGINE_DIR/prompts/topic-method.md` using `editorial.archetypes` as the
topic territory — including its DataForSEO vet step (`scripts/keywords.py vet`),
which turns the candidate pool into a data-ranked calendar for pennies (results
cache in `autoblog/keywords-cache.json`; a SKIPPED vet degrades to heuristics,
never blocks). Produce a calendar table — one row per post: date, title, slug,
priority keyword, volume, kd, cluster, search intent, 3–4 assigned related-guide
links, 2–4 must-cover bullets (including the SERP-gap/information-gain angle for
researched topics) — plus 3 reserve topics as fact-check replacements.

Hard rules: no intent overlap with any existing slug or title; about
`editorial.commercialPostsPerWeek` commercial posts per week, informational the rest;
seasonal topics `editorial.seasonalLeadWeeks` weeks ahead of their peak; assigned
links only to posts already live or dated earlier within this batch; day-to-day
cluster variety. Save the calendar to `autoblog/calendar-<first-date>.md` on the
branch (reviewers read it; the audit uses it).

**If `AUTOBLOG_DRY_RUN=true`**: write the FULL calendar, then only the first 2 posts
(Phases 2–5 for those two), commit to the branch, push, print a summary, and STOP.
Do not open a PR.

## Phase 2 — Write

1. Instantiate `$AUTOBLOG_ENGINE_DIR/prompts/writer-spec-template.md`: fill the
   placeholders from config (`site`, `editorial.audience/funnel/voice`, frontmatter
   contract from `content.frontmatter`, `ctaSnippet`, word count, banned phrases,
   hard rules) and append the linkable-post list (slug — title of every existing
   post). Save as `tmp/writer-spec.md` (git-ignored or removed before commit).
2. Spawn parallel writer subagents (~5 posts each, best model). Each prompt contains:
   the spec path, its assigned calendar rows verbatim, and the resume rule (skip
   files that already exist and end with the CTA snippet).

## Phase 3 — Validate (deterministic gates)

```sh
python3 $AUTOBLOG_ENGINE_DIR/scripts/validate.py    --config $AUTOBLOG_CONFIG --scope future
python3 $AUTOBLOG_ENGINE_DIR/scripts/sourcecheck.py --config $AUTOBLOG_CONFIG --scope future
```
Fix every error yourself. Rerun until both exit 0. `sourcecheck` fails the batch on any
**dead** cited URL (a broken citation is unpublishable under auto-merge) — fix the
citation or drop the claim; `BLOCKED` (host bot-wall, e.g. a 403) is a warning to
eyeball, not a failure.

## Phase 4 — Fact-check (skip only if `quality.factCheck` is false)

Under unattended auto-merge (see Phase 6) the gates ARE the reviewer, so this phase runs
two independent passes — do not collapse them:

**4a — Verify.** Spawn 2–3 parallel checker subagents (best model, report-only),
splitting the new posts. Each checker: for every assigned post, identify the 2–3 most
specific factual systems it states (dates, codes, named systems, laws, numbers), verify
them with web search against authoritative references, and report only confident
contradictions — citing the URL — plus any claim that violates `editorial.hardRules`.

**4b — Independent adversarial refutation (different model).** Spawn a SEPARATE checker
whose job is to *refute*, not confirm — ideally on a different model than the writers
(the `codex-implementer` agent reaches gpt-5.5) so a single model's blind spots don't
pass unchecked. For each post it takes the riskiest 2–3 claims and actively tries to
prove them wrong, defaulting to "flag it" when a source is ambiguous. A claim that
survives both 4a and 4b stays; anything flagged and unresolved is treated as a defect.

Apply fixes yourself; **replace any post with an unresolved factual doubt** with a
reserve topic (rerun Phase 2–3 for replacements). Rerun Phase 3 after edits.

## Phase 4c — Quality rubric gate

Spawn one judge subagent (best model). It scores each post 0–100 against the editorial
bar: does the opening directly answer the priority keyword; is every figure sourced; is
it free of filler/keyword-stuffing; does it honor voice + `editorial.hardRules`; is the
information-gain angle actually delivered. Any post below **70** is regenerated (rerun
Phase 2 for it) or, if it can't clear the bar, replaced with a reserve topic. This is
the automated stand-in for the human read that auto-merge removes — hold the line.

## Phase 5 — Images

If `images.ai.enabled` is true, follow `$AUTOBLOG_ENGINE_DIR/prompts/image-method.md`:
generate a real photographic hero per post via the free-image (ChatGPT) skill,
**review every card and regenerate anything not excellent**, and fall back to the
deterministic template only when no excellent image can be produced. If
`images.ai.enabled` is false, just run the template generator:
`python3 $AUTOBLOG_ENGINE_DIR/scripts/hero.py generate --config $AUTOBLOG_CONFIG`.

Then confirm no near-duplicates:
```sh
python3 $AUTOBLOG_ENGINE_DIR/scripts/dupcheck.py --config $AUTOBLOG_CONFIG
```
Dupcheck must exit 0 — a failure means real near-duplication: replace the offending topic.

## Phase 6 — Ship

1. **Reverse-link pass**: for each new post, find its closest older cluster-sibling
   already live and plan one link to the new post in that sibling's related-guides
   list (replace the weakest link if the list is at 4; never self-link). This is why
   new posts don't rank as orphans. TIMING RULE (hard): a live/published post may
   only carry links to posts that are ALREADY live — a link to a future-dated queue
   post 404s on every build until the target publishes and fails the site's SEO
   gate. So: apply the link NOW only if the new post's date has already arrived;
   otherwise record it in the ledger under `pending_reverse_links`
   (`[{"from": "<sibling-slug>", "to": "<new-slug>", "after": "<publish-date>"}]`).
   At the START of every reverse-link pass, first apply + clear any
   `pending_reverse_links` whose `after` date has passed.
2. Update `autoblog/ledger.json`: append every new topic (`status: "scheduled"`,
   with slug/keyword/cluster/date — plus `volume`/`kd` when the vet ran), move used
   candidates out of `candidates`, record rejected topics under `rejected` with
   reasons (`"dead keyword (vol 0)"` beats `"weak"`), refresh `generated_at`.
3. Run the gate scripts once yourself and fix anything they flag (so the branch is
   already clean before it leaves you):
   `python3 $AUTOBLOG_ENGINE_DIR/scripts/validate.py --config $AUTOBLOG_CONFIG --scope future`,
   `python3 $AUTOBLOG_ENGINE_DIR/scripts/sourcecheck.py --config $AUTOBLOG_CONFIG --scope future`,
   and `python3 $AUTOBLOG_ENGINE_DIR/scripts/dupcheck.py --config $AUTOBLOG_CONFIG`.
4. Write `autoblog/pr-body-<first-date>.md` on the branch — the PR description the
   harness will use: the calendar table, a **keyword-data line** (`validated via
   DataForSEO ($x.xx spent)` or `heuristic — <skip reason>`), fact-check corrections
   applied (what changed and why), topics replaced/rejected, and **the date the
   queue runs dry again**.
5. Remove `tmp/` artifacts. Commit everything (posts, images, calendar, pr-body,
   ledger, sibling edits) with message
   `autoblog: refill <first-date>..<last-date> (<n> posts)` and push the branch.
   **Stop here — do NOT open a PR or merge.** The runner (local weekly job or CI)
   re-runs the full deterministic gate chain and decides landing per `autonomy.merge`:
   `review` → opens a PR for a human; `auto` → merges automatically, but ONLY when the
   entire chain is green (validate + sourcecheck + dupcheck + the site's `check:seo`)
   AND Phases 4a/4b/4c recorded no unresolved factual or quality defect. Under `auto`
   the gates are the reviewer — a red gate blocks the merge and falls back to a PR, it
   never ships. This keeps the landing decision in deterministic tooling, not the LLM.
6. Print a final summary line: window, post count, corrections, branch, next dry date.
