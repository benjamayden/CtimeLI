#!/usr/bin/env bash
# Bootstrap venv + deps. Optionally add `ctimeli` to ~/.zshrc (runs watch mode).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$ROOT/.venv"
ZSHRC="${ZDOTDIR:-$HOME}/.zshrc"
MARKER_START="# >>> ctimeli >>>"
MARKER_END="# <<< ctimeli <<<"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "CtimeLI is macOS only." >&2
  exit 1
fi

echo "Installing in $ROOT"

if [[ ! -x "$VENV/bin/python" ]]; then
  echo "→ Creating .venv"
  python3 -m venv "$VENV"
else
  echo "→ .venv exists"
fi

echo "→ Installing PyObjC (requirements.txt)"
"$VENV/bin/pip" install -q -r "$ROOT/requirements.txt"

echo "→ Installing ctimeli (editable)"
"$VENV/bin/pip" install -q -e "$ROOT"

cp -n "$ROOT/.env.example" "$ROOT/.env"
echo "→ Env: $ROOT/.env"

echo "Installed. Try: $ROOT/run watch"

_add_zshrc() {
  local tmp
  tmp="$(mktemp)"
  if [[ -f "$ZSHRC" ]] && grep -qF "$MARKER_START" "$ZSHRC"; then
    awk -v start="$MARKER_START" -v end="$MARKER_END" '
      $0 == start { skip = 1; next }
      $0 == end   { skip = 0; next }
      !skip
    ' "$ZSHRC" > "$tmp"
    mv "$tmp" "$ZSHRC"
  fi

  {
    echo ""
    echo "$MARKER_START"
    echo "ctimeli() {"
    echo "  \"$ROOT/run\" watch \"\$@\""
    echo "}"
    echo "$MARKER_END"
  } >> "$ZSHRC"

  echo "Added ctimeli → watch in $ZSHRC"
  echo "Run: source \"$ZSHRC\"  (or open a new terminal)"
}

if [[ "${INSTALL_ZSHRC:-}" == "1" ]]; then
  _add_zshrc
else
  read -r -p "Add 'ctimeli' to ~/.zshrc (starts watch mode)? [y/N] " ans
  case "${ans}" in
    y|Y|yes|Yes) _add_zshrc ;;
    *) echo "Skipped zshrc." ;;
  esac
fi
