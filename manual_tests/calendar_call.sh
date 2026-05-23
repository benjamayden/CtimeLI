#!/usr/bin/env bash
# Test: remote calendar call opens browser at zero — no stop overlay.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "CALENDAR CALL TEST"
echo "  1. Ensure you are NOT on a work Wi-Fi SSID listed in WORK_WIFI_SSIDS."
echo "  2. Create a calendar event ~3 min from now with a Zoom/Meet URL in the URL field."
echo "  3. Press Enter to start watch mode with BLOCK_ON_END=true."
printf "\n  Press Enter… "; read -r

BLOCK_ON_END=true ./run watch || true

echo
echo "  • Countdown auto-started for the event?"
echo "  • At zero: browser opened the meeting URL?"
echo "  • NO full-screen stop overlay appeared?"
echo "  • Browser stayed open/foreground (not minimised)?"
printf "\n  Pass? [y/n]: "; read -r ans
[[ "$ans" == y* ]] && echo "PASS" || echo "FAIL"
