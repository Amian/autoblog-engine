# autoblog-engine

A generic, set-and-forget blog generation system for static sites. One config file
turns any site repo (Jekyll, Astro, plain markdown) into a self-refilling,
quality-gated, SEO-focused blog.

**Core principle: AI never sits in the publish path.**

- Posts live in git as a **future-dated queue**, written weeks ahead.
- **Daily publish** is a dumb scheduled rebuild — deterministic, effectively cannot fail.
- A **weekly refill** runs Claude in GitHub Actions *only when the queue is low*,
  and its output lands as a pull request.
- **CI quality gates** (no AI) validate every post before it enters the queue.
- A **watchdog** and **monthly audit** close the loop.

## Adopt it for a site

See [docs/SITE-SETUP.md](docs/SITE-SETUP.md). In short: add `autoblog.config.json`,
seed `autoblog/ledger.json`, copy the 3 caller workflows from
[caller-templates/](caller-templates/), and add a `CLAUDE_CODE_OAUTH_TOKEN` secret.

## Docs

- [docs/PLAN.md](docs/PLAN.md) — the project plan (why, decisions, phases)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — how the system works
- [docs/CONFIG.md](docs/CONFIG.md) — `autoblog.config.json` reference
- [docs/SITE-SETUP.md](docs/SITE-SETUP.md) — onboard a new site (~30 min)
- [docs/RUNBOOK.md](docs/RUNBOOK.md) — operations + failure modes

## Layout

```
.github/workflows/   reusable workflows (refill, gates, watchdog, audit, publish)
prompts/             instructions the CI agent follows (refill, audit, onboard, …)
scripts/             stdlib Python: runway, validate, dupcheck, linkcheck, hero, ledger, keywords (DataForSEO)
schema/              JSON Schema for autoblog.config.json
caller-templates/    thin workflow files copied into site repos
docs/                plan + reference documentation
```

Site repos pin `@v1`; improvements to the engine propagate to every site without
touching the site repos.
