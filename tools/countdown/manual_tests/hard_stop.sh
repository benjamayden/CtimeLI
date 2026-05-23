#!/usr/bin/env bash
# Test: end-of-day hard stop — orange stroke in watch mode.
set -euo pipefail
cd "$(dirname "$0")/.."

# Hard stop ~3 minutes from now (within the 30-minute warning window).
target_time=$(date -v+3M "+%H:%M")

echo "HARD STOP TEST"
echo "  HARD_STOP_TIME will be set to $target_time (about 3 minutes from now)."
echo "  Press Enter to start watch mode."
printf "\n  Press Enter… "; read -r

HARD_STOP_ENABLED=true \
HARD_STOP_TIME="$target_time" \
HARD_STOP_WARNING_MINS=30 \
BLOCK_ON_END=true \
./run watch || true

echo
echo "  • Orange stroke appeared (not blue/green)?"
echo "  • HUD showed 'hard stop $target_time' suffix?"
echo "  • At zero: stop overlay said 'End of day' / 'Hard stop'?"
printf "\n  Pass? [y/n]: "; read -r ans
[[ "$ans" == y* ]] && echo "PASS" || echo "FAIL"
