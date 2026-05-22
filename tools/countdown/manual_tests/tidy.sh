#!/usr/bin/env bash
# Test: window tidy (minimize/hide) — open a few apps first.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "TIDY TEST  (minimize/hide)"
echo "  Open a few apps with visible windows (e.g. Safari, Notes, TextEdit)."
printf "\n  Press Enter when ready… "; read -r

./run 0.01 --block-on-end || true

echo
echo "  • Overlay dismissed → windows minimized into the Dock?"
echo "  • Terminal printed 'Block end: minimized N windows.'?"
echo "  • Terminal regained focus after cleanup?"
printf "\n  Pass? [y/n]: "; read -r ans
[[ "$ans" == y* ]] && echo "PASS" || echo "FAIL"
