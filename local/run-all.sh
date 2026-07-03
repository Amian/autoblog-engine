#!/usr/bin/env bash
# Weekly entrypoint (launchd runs this). Refills every registered site.
# Registry: ~/.autoblog/sites.txt — one site-repo ABSOLUTE path per line, # comments ok.
# Add a site = add a line. Continues past a failing site; each notifies for itself.
set -uo pipefail

ENGINE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REG="${AUTOBLOG_SITES:-$HOME/.autoblog/sites.txt}"
LOGDIR="${AUTOBLOG_LOGDIR:-$HOME/.autoblog/logs}"
mkdir -p "$LOGDIR"

# Make common CLIs reachable under launchd's minimal PATH.
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

echo "$(date '+%F %T')  run-all starting (registry: $REG)" >> "$LOGDIR/summary.log"
if [ ! -f "$REG" ]; then
  echo "$(date '+%F %T')  no registry at $REG — nothing to do" >> "$LOGDIR/summary.log"
  exit 0
fi

rc=0
while IFS= read -r line; do
  line="${line%%#*}"; line="$(echo "$line" | xargs)"   # strip comments + whitespace
  [ -z "$line" ] && continue
  echo "$(date '+%F %T')  → refilling $line" >> "$LOGDIR/summary.log"
  "$ENGINE/refill-once.sh" "$line" "$@" || { rc=1; echo "$(date '+%F %T')  ✗ $line failed" >> "$LOGDIR/summary.log"; }
done < "$REG"

echo "$(date '+%F %T')  run-all done (rc=$rc)" >> "$LOGDIR/summary.log"
exit $rc
