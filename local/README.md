# Local weekly runner

Runs blog generation **on your Mac** instead of GitHub Actions, using your logged-in
Claude subscription (`claude -p`). Use this when the subscription token can't run
Claude headless in the cloud but works locally — the common case for personal plans.

Only *generation* is local. Publishing stays as the site's own scheduled rebuild, and
the GitHub **watchdog** keeps running in the cloud as an independent "did my Mac do its
job" alarm.

## What it does each Saturday 09:00 (local)

For every site in `~/.autoblog/sites.txt`:
1. Pull the repo's default branch (aborts if the working tree is dirty — never touches
   your uncommitted work).
2. Check queue runway; if healthy, stop (no tokens spent).
3. If low, run `claude -p` with the engine's `prompts/refill.md` — research, write,
   fact-check, hero images, all on the best model.
4. Re-run the deterministic gates (validate, dupcheck, hero verify, build, linkcheck).
5. On green, open a PR (default) or merge to main (`--auto` / `autonomy.merge: "auto"`).
6. Send a macOS notification with the outcome + PR link.

A failed generation is caught (the run JSON's `is_error`) and **never** opens a PR.

## Install (once)

```sh
~/Development/autoblog-engine/local/install.sh
```
Creates `~/.autoblog/`, seeds the site registry from `sites.txt.example`, and loads the
launchd agent. Edit `~/.autoblog/sites.txt` to list your site repos (absolute paths).

## Use it by hand

```sh
local/refill-once.sh <site-repo> --dry-run   # calendar + 2 sample posts on a branch, no PR
local/refill-once.sh <site-repo>             # full batch → PR (respects runway; add --force to override)
local/refill-once.sh <site-repo> --force --auto   # full batch, merge straight to main
local/run-all.sh --dry-run                   # dry-run every registered site
```

Test the scheduled path without waiting for Saturday:
```sh
launchctl kickstart -k gui/$(id -u)/com.autoblog.weekly
tail -f ~/.autoblog/logs/summary.log
```

## Onboard a new app

1. Wire the repo (config + ledger + gates/watchdog callers) per `docs/SITE-SETUP.md`.
2. Add its absolute path to `~/.autoblog/sites.txt`.
That's it — the weekly job now covers it.

## Notes / trust

- Generation uses `--permission-mode bypassPermissions`: `claude -p` runs full Bash in
  your own repo, driven by the trusted engine prompt — the same trust boundary as
  interactive Claude Code. Don't point the registry at repos you don't control.
- `--max-budget-usd` (default 25, override `AUTOBLOG_MAX_USD`) caps spend per run. With
  subscription auth this mostly bounds a runaway loop; if you hit a usage limit
  mid-batch the run stops and the next week resumes idempotently.
- If the Mac is asleep at 09:00 Saturday, launchd runs the job at the next wake.
- Auth under launchd uses your login keychain / `~/.claude`; it works while you're
  logged in. If a scheduled run ever fails auth but manual runs work, run
  `local/refill-once.sh <site> --dry-run` once in a terminal to confirm, and make sure
  you're logged into the GUI session.
