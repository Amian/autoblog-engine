#!/usr/bin/env bash
# One-time setup for the local weekly runner. Idempotent — safe to re-run.
#   local/install.sh
# Creates ~/.autoblog, seeds the site registry, renders + loads the launchd agent
# (Saturday 09:00). Re-run after editing the plist template to reload.
set -euo pipefail

ENGINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.autoblog.weekly"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
CONF="$HOME/.autoblog"

mkdir -p "$CONF/logs"
if [ ! -f "$CONF/sites.txt" ]; then
  cp "$ENGINE/local/sites.txt.example" "$CONF/sites.txt"
  echo "seeded $CONF/sites.txt (edit it to list your site repos)"
else
  echo "$CONF/sites.txt already exists — left as is"
fi

chmod +x "$ENGINE/local/refill-once.sh" "$ENGINE/local/run-all.sh"

sed -e "s|__ENGINE__|$ENGINE|g" -e "s|__HOME__|$HOME|g" \
  "$ENGINE/local/com.autoblog.weekly.plist.template" > "$PLIST"
echo "wrote $PLIST"

# Reload under the modern launchctl API (bootout may fail if not loaded — ignore).
UID_NUM="$(id -u)"
launchctl bootout "gui/$UID_NUM/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$UID_NUM" "$PLIST"
launchctl enable "gui/$UID_NUM/$LABEL"
echo "loaded launchd agent $LABEL (Saturdays 09:00 local)"
echo
echo "Verify:   launchctl print gui/$UID_NUM/$LABEL | grep -A2 'state\\|runs'"
echo "Test now: launchctl kickstart -k gui/$UID_NUM/$LABEL   (runs the real weekly job)"
echo "Logs:     tail -f $CONF/logs/summary.log"
