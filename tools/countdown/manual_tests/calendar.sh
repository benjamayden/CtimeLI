#!/usr/bin/env bash
# Test: watch mode calendar auto-start + green colour.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "CALENDAR TEST"
echo "  1. Open Calendar and create an event starting 3–5 minutes from now."
echo "  2. Come back here and press Enter."
echo "  3. Wait up to ~15 s for the countdown to auto-start."
echo "  4. Check the colour and HUD label, then Ctrl+C to exit."
printf "\n  Press Enter to start watch mode… "; read -r

./run watch || true

echo
echo "  • Countdown auto-started within ~15 s (no manual input)?"
echo "  • Stroke was GREEN (calendar colour, not the default blue)?"
echo "  • HUD showed the event time as a suffix (e.g. '· 14:30')?"
printf "\n  Pass? [y/n]: "; read -r ans
[[ "$ans" == y* ]] && echo "PASS" || echo "FAIL"
