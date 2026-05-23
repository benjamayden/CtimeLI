#!/usr/bin/env bash
# Test: calendar event with physical room shows room on stop overlay.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "CALENDAR ROOM TEST"
echo "  1. Create a calendar event ~3 min from now."
echo "  2. Set Location to a room name (e.g. 'Room 3A') — no meeting URL."
echo "  3. Press Enter to start watch mode with BLOCK_ON_END=true."
printf "\n  Press Enter… "; read -r

BLOCK_ON_END=true ./run watch || true

echo
echo "  • At zero: stop overlay showed the room name?"
echo "  • No browser opened?"
echo "  • Dismiss → windows tidied as usual?"
printf "\n  Pass? [y/n]: "; read -r ans
[[ "$ans" == y* ]] && echo "PASS" || echo "FAIL"
