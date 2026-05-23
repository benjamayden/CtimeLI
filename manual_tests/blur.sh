#!/usr/bin/env bash
# Manual blur checklist — run from repo root
set -euo pipefail
cd "$(dirname "$0")/.."

echo "BLUR TEST"
echo "  Uses PULSE_* settings from .env (blur shares the glow window)."
echo "  Run a short timer with block-on-end and watch the desktop blur in."
echo ""
./run 2 --block-on-end

echo ""
echo "  • Desktop blurred progressively toward zero?"
echo "  • Stop overlay showed blurred background?"
echo "  • Click dismissed both block and blur?"
