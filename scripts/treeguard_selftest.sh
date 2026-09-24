#!/usr/bin/env bash
# Self-test for treeguard.py. Stdlib/git only, no network, no fixtures.
#   bash scripts/treeguard_selftest.sh
# Exits 0 if every case behaves; prints the first failure otherwise.
#
# Why this exists: treeguard gates an unattended routine. A regression here either
# freezes every content queue (blocks when it should proceed) or, far worse, loses
# someone's uncommitted work. Both are silent until days later.
set -uo pipefail

TG="$(cd "$(dirname "$0")" && pwd)/treeguard.py"
ROOT="$(mktemp -d)"
trap 'rm -rf "$ROOT"' EXIT
fails=0

new_repo() {
  local d="$ROOT/$1"; rm -rf "$d"; mkdir -p "$d"; cd "$d"
  git init -q .; git config user.email t@t.t; git config user.name T
  echo original > post.md; echo keep > other.md
  git add -A; git commit -q -m init
}
check() { # check <label> <expected-exit> <actual-exit>
  if [ "$2" = "$3" ]; then echo "  ok   $1"; else echo "  FAIL $1 (expected exit $2, got $3)"; fails=$((fails+1)); fi
}

echo "case 1: clean tree proceeds"
new_repo c1
python3 "$TG" --repo . --clean --park >/dev/null 2>&1; check "clean -> 0" 0 $?

echo "case 2: throwaway artifacts are cleaned, not parked"
new_repo c2
echo x > run.log; mkdir -p tmp; echo y > tmp/scratch
python3 "$TG" --repo . --clean --park >/dev/null 2>&1; check "throwaway -> 0" 0 $?
[ -z "$(git status --porcelain)" ] && echo "  ok   tree clean after throwaway sweep" \
  || { echo "  FAIL tree still dirty"; fails=$((fails+1)); }
[ -z "$(git branch --list 'salvage/*')" ] && echo "  ok   no salvage branch for throwaway" \
  || { echo "  FAIL throwaway got parked onto a branch"; fails=$((fails+1)); }

echo "case 3: real changes are parked and fully recoverable"
new_repo c3
echo "EDITED BY A KILLED RUN" >> post.md
echo "half written" > newpost.md
python3 "$TG" --repo . --clean --park >/dev/null 2>&1; check "real -> 0 (parked)" 0 $?
[ -z "$(git status --porcelain)" ] && echo "  ok   tree returned to clean" \
  || { echo "  FAIL tree still dirty after park"; fails=$((fails+1)); }
B="$(git branch --list 'salvage/*' | tr -d ' *' | head -1)"
[ -n "$B" ] && echo "  ok   salvage branch created ($B)" \
  || { echo "  FAIL no salvage branch"; fails=$((fails+1)); }
[ "$(cat post.md)" = "original" ] && echo "  ok   working copy restored to HEAD" \
  || { echo "  FAIL working copy not restored"; fails=$((fails+1)); }
if [ -n "$B" ]; then
  git show "$B":post.md 2>/dev/null | grep -q "EDITED BY A KILLED RUN" \
    && echo "  ok   tracked edit recoverable" \
    || { echo "  FAIL tracked edit LOST"; fails=$((fails+1)); }
  git show "$B":newpost.md 2>/dev/null | grep -q "half written" \
    && echo "  ok   untracked file recoverable" \
    || { echo "  FAIL untracked file LOST"; fails=$((fails+1)); }
fi

echo "case 4: without --park, real changes still block"
new_repo c4
echo "edit" >> post.md
python3 "$TG" --repo . --clean >/dev/null 2>&1; check "no --park -> 2" 2 $?

echo "case 5: refuses to park mid-merge"
new_repo c5
git checkout -q -b side; echo side > post.md; git commit -qam side
git checkout -q -; echo mainline > post.md; git commit -qam mainline
git merge side >/dev/null 2>&1
python3 "$TG" --repo . --clean --park >/dev/null 2>&1; check "mid-merge -> 2" 2 $?

echo
if [ "$fails" -eq 0 ]; then echo "treeguard selftest: all cases passed"; else echo "treeguard selftest: $fails FAILURE(S)"; fi
exit $([ "$fails" -eq 0 ] && echo 0 || echo 1)
