#!/usr/bin/env bash
# Test: border stroke only — 3-minute timer so glow hasn't started yet
# (glow window opens at 2 min remaining). Press Ctrl+C after ~5 s.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "STROKE TEST  (Ctrl+C after ~5 s)"
echo "  Running a 3-minute timer — glow doesn't start until 2 min remaining."
echo "  Watch the border for a few seconds, then Ctrl+C."
echo
./run 3 || true

echo
echo "  • Coloured stroke around the full perimeter of every display?"
echo "  • Stroke shrinking clockwise?"
echo "  • No edge glow visible yet?"
printf "\n  Pass? [y/n]: "; read -r ans
[[ "$ans" == y* ]] && echo "PASS" || echo "FAIL"
