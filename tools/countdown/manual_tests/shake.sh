#!/usr/bin/env bash
# Test: window wiggle only — no countdown overlay at all.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "SHAKE TEST"
echo "  Open TextEdit (or any non-terminal window) and click it"
echo "  to make it frontmost. Come back here when ready."
printf "\n  Press Enter to start… "; read -r

./shake --seconds 5 --intensity 1

echo
echo "  • Window oscillated left/right for ~5 s?"
echo "  • Snapped back exactly to its original position?"
echo "  • No countdown overlay — wiggle only?"
printf "\n  Pass? [y/n]: "; read -r ans
[[ "$ans" == y* ]] && echo "PASS" || echo "FAIL"
