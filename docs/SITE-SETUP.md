# Onboard a site (~30 minutes)

Works for any static-site repo on GitHub. The fastest path: open the site repo in
Claude Code and say *"wire this repo into autoblog-engine, follow
https://github.com/Amian/autoblog-engine/blob/main/prompts/onboard.md"* — the onboard
prompt automates steps 2–5. Manual steps below.

## 0. Prerequisites
- The site builds statically in CI (Jekyll, Astro, Hugo, plain HTML — anything).
- A daily publish mechanism exists or you'll add the engine's `publish.yml`
  (posts must be date-gated: Jekyll `future: false`, or an SSG build filter).
- Repo is on GitHub with Actions enabled.

## 1. Human-required setup (two parts — both needed before refill works)

**a. Install the Claude GitHub App** on the site repo — visit
https://github.com/apps/claude and grant it access to this repo (or run `claude`
locally and use `/install-github-app`). Without this, refill fails with
"Claude Code is not installed on this repository". The OAuth token *authorizes*
Claude; the App is what lets it *run* inside the repo's Actions. Both are required.

**b. Secrets** — site repo → Settings → Secrets and variables → Actions:
- `CLAUDE_CODE_OAUTH_TOKEN` — run `claude setup-token` locally, paste the token.
- `CLOUDFLARE_DEPLOY_HOOK` — only if using the engine's `publish.yml`.
- `GSC_CREDENTIALS` — optional; Search Console service-account JSON, enables audits.

## 2. `autoblog.config.json`
Copy the shape from [CONFIG.md](CONFIG.md). The editorial section deserves real
thought — audience, funnel, voice, and rich archetypes with examples. Everything
subject-specific lives here; the engine stays generic.

## 3. Topic ledger
```sh
python3 <engine>/scripts/ledger.py seed --config autoblog.config.json \
  [--backlog _data/content_backlog.yml]
```
Inventories every existing post into `autoblog/ledger.json` as `covered`, and
imports backlog candidates if you have them.

## 4. Caller workflows
Copy the 3 files from `caller-templates/` into `.github/workflows/`:
- `autoblog-refill.yml` — weekly cron + manual dispatch (`force`, `dry_run`, `days`)
- `autoblog-gates.yml` — runs on PRs touching the content dir
- `autoblog-watchdog.yml` — daily runway check

They only reference `Amian/autoblog-engine/.github/workflows/*@v1` — no logic to maintain.
If the site has no daily publish yet, also copy `autoblog-publish.yml`.

## 5. Verify before trusting cron
1. **Gates on the existing corpus**: open a trivial PR touching the content dir —
   gates must pass. If they flag existing posts, fix the config (usually
   `frontmatter.required` too strict) until the real corpus is green.
2. **Watchdog**: dispatch it manually — with a healthy queue it should do nothing.
3. **Dry run**: dispatch `autoblog-refill` with `dry_run: true` — it writes 2 posts +
   a calendar to a branch and stops. Read them. This is your quality preview.
4. **First real batch**: dispatch with `force: true` → review the PR like an editor,
   not a proofreader (the gates proofread). Merge.
5. After 2–3 clean batches, set `"autonomy": { "merge": "auto" }`. From then on you
   only hear from the system when something needs you.

## What "set and forget" looks like after this
- Refill tops the queue up weekly (skips itself when healthy — zero cost).
- Gates guard every merge. Watchdog + GitHub failure emails are the only alarms.
- Optional: ~15 min/month skimming the audit issue makes the loop compound faster.
