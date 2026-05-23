#!/usr/bin/env bash
# Test: edge glow — 2-minute timer so glow starts from the first frame.
# Press Ctrl+C after ~15 s once you've seen it bloom.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "GLOW TEST  (Ctrl+C after ~15 s)"
echo "  Running a 2-minute timer — glow is active from the first frame."
echo "  Watch the screen edges bloom inward, then Ctrl+C."
echo
./run 2 || true

echo
echo "  • Soft glow bloomed inward from all screen edges?"
echo "  • Glow deepened as time passed?"
printf "\n  Pass? [y/n]: "; read -r ans
[[ "$ans" == y* ]] && echo "PASS" || echo "FAIL"
