#!/usr/bin/env bash
# Test: stop overlay only — sub-second countdown so it fires almost immediately.
# BLOCK_END_DEFAULT=none means no window tidy happens after dismissal.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "BLOCK SCREEN TEST  (overlay only, no window tidy)"
echo "  A sub-second countdown fires then the stop overlay appears."
echo
BLOCK_END_DEFAULT=none ./run 0.01 --block-on-end || true

echo
echo "  • Dark overlay covered every screen?"
echo "  • Cursor hidden while overlay was up?"
echo "  • Clicks in the first ~0.6 s did nothing (lockout)?"
echo "  • Click / Return / Escape dismissed it cleanly?"
echo "  • No windows were moved or minimized?"
printf "\n  Pass? [y/n]: "; read -r ans
[[ "$ans" == y* ]] && echo "PASS" || echo "FAIL"
