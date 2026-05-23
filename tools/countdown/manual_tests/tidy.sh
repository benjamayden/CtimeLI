#!/usr/bin/env bash
# Test: window tidy (hide others + minimize focused) — open a few apps first.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "TIDY TEST  (hide others + minimize focused)"
echo "  Open a few apps with visible windows (e.g. Safari, Notes, TextEdit)."
echo "  Focus one app (e.g. Notes) before the timer ends."
printf "\n  Press Enter when ready… "; read -r

./run 0.01 --block-on-end || true

echo
echo "  • Overlay dismissed instantly (no multi-second stall)?"
echo "  • Other apps hidden (not Dock-minimized)?"
echo "  • Focused app minimized into the Dock?"
echo "  • Terminal printed 'Block end: hid other apps, minimized focused window.'?"
echo "  • Terminal regained focus after cleanup?"
printf "\n  Pass? [y/n]: "; read -r ans
[[ "$ans" == y* ]] && echo "PASS" || echo "FAIL"
