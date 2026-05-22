#!/usr/bin/env bash
# Run all manual tests in sequence, or one by name.
# Usage:
#   ./test_manual.sh                  — run all
#   ./test_manual.sh shake
#   ./test_manual.sh stroke
#   ./test_manual.sh glow
#   ./test_manual.sh block_screen
#   ./test_manual.sh tidy
#   ./test_manual.sh calendar

set -euo pipefail
cd "$(dirname "$0")"

TESTS=(shake stroke glow block_screen tidy calendar)

run_test() {
    bash "manual_tests/$1.sh"
}

case "${1:-all}" in
    all)
        pass=0; fail=0
        for t in "${TESTS[@]}"; do
            echo; echo "────────────────────────────────────"
            result=$(run_test "$t" && echo ok || echo fail)
            [[ "$result" == ok ]] && pass=$((pass+1)) || fail=$((fail+1))
        done
        echo; echo "━━ $pass passed, $fail failed ━━"
        ;;
    shake|stroke|glow|block_screen|tidy|calendar)
        run_test "$1"
        ;;
    *)
        echo "Unknown: $1"
        echo "Valid: ${TESTS[*]} | all"
        exit 1
        ;;
esac
