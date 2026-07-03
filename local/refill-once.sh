#!/usr/bin/env bash
# Refill ONE site's blog queue, locally, using the logged-in Claude subscription.
# Generation runs via `claude -p` (headless print mode) — same auth as interactive
# Claude Code, so it sidesteps the cloud/headless entitlement limit that blocks
# GitHub Actions. Then the deterministic gates run; on green, a PR is opened.
#
#   refill-once.sh <site-repo-abs-path> [--force] [--dry-run] [--auto] [--model X]
#
# --force     refill even if the queue is healthy
# --dry-run   write only the calendar + 2 posts to a branch; no PR (quality preview)
# --auto      merge to main instead of opening a PR (overrides config autonomy.merge)
# --model X   CLI model alias/id (default: opus)
#
# Exit 0 = success or nothing-to-do; non-zero = a real failure (notified).
set -euo pipefail

ENGINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOGDIR="${AUTOBLOG_LOGDIR:-$HOME/.autoblog/logs}"
mkdir -p "$LOGDIR"

# Optional auth/config overrides. Put `export ANTHROPIC_API_KEY=...` here to run the
# generator on a metered API key instead of the interactive subscription (the reliable
# path if headless `claude -p` can't use your subscription).
[ -f "$HOME/.autoblog/env" ] && . "$HOME/.autoblog/env"

SITE="" ; FORCE=0 ; DRY=0 ; AUTO=0 ; MODEL="opus"
while [ $# -gt 0 ]; do
  case "$1" in
    --force) FORCE=1 ;;
    --dry-run) DRY=1 ;;
    --auto) AUTO=1 ;;
    --model) MODEL="$2"; shift ;;
    -*) echo "unknown flag: $1" >&2; exit 2 ;;
    *) SITE="$1" ;;
  esac
  shift
done
[ -n "$SITE" ] || { echo "usage: refill-once.sh <site-repo-abs-path> [--force] [--dry-run] [--auto]" >&2; exit 2; }
SITE="$(cd "$SITE" && pwd)"
NAME="$(basename "$SITE")"
STAMP="$(date +%Y-%m-%d-%H%M)"
RUNLOG="$LOGDIR/${NAME}-${STAMP}.json"

notify() { # notify "title" "message"
  osascript -e "display notification \"$2\" with title \"autoblog: $1\"" 2>/dev/null || true
  echo "$(date '+%F %T')  [$NAME]  $1 — $2" >> "$LOGDIR/summary.log"
}
fail() { notify "FAILED ($NAME)" "$1"; echo "ERROR: $1" >&2; exit 1; }

command -v claude >/dev/null || fail "claude CLI not found on PATH"
command -v gh >/dev/null || fail "gh CLI not found on PATH"
[ -f "$SITE/autoblog.config.json" ] || fail "no autoblog.config.json in $SITE"

cd "$SITE"

# 1. Sync main; never disturb uncommitted work.
if [ -n "$(git status --porcelain)" ]; then
  fail "working tree not clean in $SITE — refusing to run (commit or stash first)"
fi
DEFAULT_BRANCH="$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's@^origin/@@' || echo main)"
git fetch --quiet origin
git checkout --quiet "$DEFAULT_BRANCH"
git pull --quiet --ff-only

# 2. Runway gate — cheap, no tokens.
RUNWAY_JSON="$(python3 "$ENGINE/scripts/runway.py" --config autoblog.config.json)"
NEEDS="$(printf '%s' "$RUNWAY_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["needs_refill"])')"
DRY_DATE="$(printf '%s' "$RUNWAY_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["dry_date"])')"
DAYS="$(printf '%s' "$RUNWAY_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["days"])')"
if [ "$NEEDS" != "True" ] && [ "$FORCE" -ne 1 ]; then
  echo "[$NAME] queue healthy: $DAYS days left (dry $DRY_DATE) — skipping."
  exit 0
fi

BRANCH="autoblog/refill-${DRY_DATE}"
git checkout --quiet -B "$BRANCH"
echo "[$NAME] refilling on $BRANCH (dry_run=$DRY, days_left=$DAYS)"

# 3. Generate with the logged-in subscription (NOT --bare, which forces an API key).
DRY_BOOL=false; [ "$DRY" -eq 1 ] && DRY_BOOL=true
PROMPT="$(cat "$ENGINE/prompts/refill.md")

---
Execute the instructions above exactly. The engine (scripts + sibling prompts) is at
$ENGINE — use that path wherever the instructions say \$AUTOBLOG_ENGINE_DIR. You are
in the site repo $SITE on branch $BRANCH. config=autoblog.config.json,
dry_run=$DRY_BOOL, dry_date=$DRY_DATE. Use \`gh\` for the pull request."

set +e
AUTOBLOG_ENGINE_DIR="$ENGINE" \
AUTOBLOG_CONFIG="autoblog.config.json" \
AUTOBLOG_DRY_RUN="$DRY_BOOL" \
AUTOBLOG_DRY_DATE="$DRY_DATE" \
AUTOBLOG_BRANCH="$BRANCH" \
claude -p "$PROMPT" \
  --model "$MODEL" \
  --fallback-model sonnet \
  --allowedTools "Bash,Read,Write,Edit,Glob,Grep,WebSearch,WebFetch,Task,TodoWrite" \
  --permission-mode bypassPermissions \
  --max-budget-usd "${AUTOBLOG_MAX_USD:-25}" \
  --output-format json \
  > "$RUNLOG" 2>>"$LOGDIR/${NAME}-${STAMP}.stderr.log"
CLAUDE_RC=$?
set -e

# 4. Error guard — never let a failed generation look successful.
python3 - "$RUNLOG" "$CLAUDE_RC" <<'PY' || fail "generation errored (see $RUNLOG) — no PR opened"
import json, sys
runlog, rc = sys.argv[1], int(sys.argv[2])
try:
    data = json.load(open(runlog))
except Exception as e:
    sys.exit(f"could not parse run log: {e}")
result = data if isinstance(data, dict) else next(
    (m for m in reversed(data) if m.get("type") == "result"), None)
if result is None:
    sys.exit("no result object in run log")
if result.get("is_error") or rc != 0:
    print(json.dumps({k: result.get(k) for k in
        ("is_error","subtype","num_turns","total_cost_usd","duration_ms")}, indent=2))
    sys.exit("Claude reported an error")
print(f"generation OK: {result.get('num_turns')} turns, "
      f"${result.get('total_cost_usd')}, {result.get('duration_ms')}ms")
PY

# 5. Deterministic gates (same scripts as CI).
CFG=autoblog.config.json
python3 "$ENGINE/scripts/validate.py" --config "$CFG" --scope future || fail "validate.py failed on the new batch"
python3 "$ENGINE/scripts/dupcheck.py" --config "$CFG" --scope future || fail "dupcheck.py found near-duplicates"
python3 "$ENGINE/scripts/hero.py" verify --config "$CFG" || fail "hero.py verify found missing images"

BUILD_CMD="$(python3 -c 'import json;print(json.load(open("autoblog.config.json"))["build"]["command"])')"
DIST="$(python3 -c 'import json;print(json.load(open("autoblog.config.json"))["build"]["distDir"])')"
echo "[$NAME] building: $BUILD_CMD"
bash -lc "$BUILD_CMD" || fail "site build failed"
python3 "$ENGINE/scripts/linkcheck.py" --dist "$DIST" || fail "linkcheck found broken links"

# 6. Land the batch.
git push --quiet -u origin "$BRANCH"
MERGE_MODE="$(python3 -c 'import json;print(json.load(open("autoblog.config.json")).get("autonomy",{}).get("merge","review"))')"
if [ "$DRY" -eq 1 ]; then
  notify "dry run ready ($NAME)" "branch $BRANCH pushed — review the 2 sample posts"
  echo "[$NAME] dry run complete — branch $BRANCH (no PR)."
  exit 0
fi
if [ "$AUTO" -eq 1 ] || [ "$MERGE_MODE" = "auto" ]; then
  git checkout --quiet "$DEFAULT_BRANCH"
  git merge --quiet --no-ff "$BRANCH" -m "autoblog: refill $DRY_DATE"
  git push --quiet origin "$DEFAULT_BRANCH"
  notify "published ($NAME)" "merged $BRANCH → $DEFAULT_BRANCH; daily rebuild will publish"
else
  BODY_FILE="autoblog/pr-body-${DRY_DATE}.md"
  if [ -f "$BODY_FILE" ]; then
    PR_ARGS=(--title "autoblog: refill $DRY_DATE" --body-file "$BODY_FILE")
  else
    PR_ARGS=(--fill)
  fi
  URL="$(gh pr create --head "$BRANCH" --base "$DEFAULT_BRANCH" "${PR_ARGS[@]}" 2>/dev/null || gh pr view "$BRANCH" --json url --jq .url)"
  notify "PR ready ($NAME)" "review + merge: ${URL:-$BRANCH}"
  echo "[$NAME] PR: ${URL:-$BRANCH}"
fi
