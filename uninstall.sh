#!/usr/bin/env bash
# Remove install artifacts: zshrc block, .venv, .env, build caches.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
ZSHRC="${ZDOTDIR:-$HOME}/.zshrc"
# Must match install.sh exactly.
MARKER_START="# >>> ctimeli >>>"
MARKER_END="# <<< ctimeli <<<"

_remove_zshrc() {
  if [[ ! -f "$ZSHRC" ]]; then
    echo "→ No $ZSHRC"
    return 0
  fi
  if ! grep -qF "$MARKER_START" "$ZSHRC"; then
    echo "→ No ctimeli block in $ZSHRC"
    return 0
  fi

  local tmp
  tmp="$(mktemp)"
  awk -v start="$MARKER_START" -v end="$MARKER_END" '
    $0 == start { skip = 1; next }
    $0 == end   { skip = 0; next }
    !skip
  ' "$ZSHRC" > "$tmp"
  mv "$tmp" "$ZSHRC"
  echo "→ Removed ctimeli block from $ZSHRC"
}

_rm_path() {
  local path="$1"
  if [[ -e "$path" || -L "$path" ]]; then
    rm -rf "$path"
    echo "→ Removed $path"
  fi
}

echo "Uninstalling CtimeLI artifacts in $ROOT"
echo ""

if [[ "${UNINSTALL_YES:-}" != "1" ]]; then
  read -r -p "Remove .venv, .env, zshrc alias, and build caches? [y/N] " ans
  case "${ans}" in
    y|Y|yes|Yes) ;;
    *) echo "Cancelled."; exit 0 ;;
  esac
fi

_remove_zshrc

_rm_path "$ROOT/.venv"
_rm_path "$ROOT/.env"
_rm_path "$ROOT/apps.manifest"

while IFS= read -r -d '' dir; do
  rm -rf "$dir"
  echo "→ Removed $dir"
done < <(find "$ROOT" -name __pycache__ -type d -print0 2>/dev/null)

while IFS= read -r -d '' dir; do
  rm -rf "$dir"
  echo "→ Removed $dir"
done < <(find "$ROOT" -name .pytest_cache -type d -print0 2>/dev/null)

while IFS= read -r -d '' dir; do
  rm -rf "$dir"
  echo "→ Removed $dir"
done < <(find "$ROOT" -name '*.egg-info' -type d -print0 2>/dev/null)

echo ""
echo "Done. Source code unchanged. Reinstall: $ROOT/install.sh"
