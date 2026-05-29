#!/usr/bin/env bash
# Bootstrap venv + deps. Optionally add `ctimeli` to ~/.zshrc (runs watch mode).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$ROOT/.venv"
ZSHRC="${ZDOTDIR:-$HOME}/.zshrc"
MARKER_START="# >>> ctimeli >>>"
MARKER_END="# <<< ctimeli <<<"
MIN_PY_MAJOR=3
MIN_PY_MINOR=11

pick_python() {
  local cands=("python3.12" "python3.11" "/opt/homebrew/bin/python3" "/usr/local/bin/python3" "python3")
  local py v maj min
  for py in "${cands[@]}"; do
    if ! command -v "$py" >/dev/null 2>&1; then
      continue
    fi
    v="$("$py" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
    maj="${v%%.*}"
    min="${v##*.}"
    if (( maj > MIN_PY_MAJOR || (maj == MIN_PY_MAJOR && min >= MIN_PY_MINOR) )); then
      echo "$py"
      return 0
    fi
  done
  return 1
}

ensure_venv_python_compatible() {
  local v maj min
  v="$("$VENV/bin/python" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
  maj="${v%%.*}"
  min="${v##*.}"
  if ! (( maj > MIN_PY_MAJOR || (maj == MIN_PY_MAJOR && min >= MIN_PY_MINOR) )); then
    echo "Existing .venv uses Python $v, but CtimeLI requires >= ${MIN_PY_MAJOR}.${MIN_PY_MINOR}." >&2
    echo "Remove it and rerun: rm -rf \"$VENV\" && ./install.sh" >&2
    exit 1
  fi
}

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "CtimeLI is macOS only." >&2
  exit 1
fi

echo "Installing in $ROOT"

if ! PY_BIN="$(pick_python)"; then
  echo "Python ${MIN_PY_MAJOR}.${MIN_PY_MINOR}+ is required. Install python3.11 or python3.12." >&2
  exit 1
fi

if [[ ! -x "$VENV/bin/python" ]]; then
  echo "→ Creating .venv with $PY_BIN"
  "$PY_BIN" -m venv "$VENV"
else
  echo "→ .venv exists"
  ensure_venv_python_compatible
fi

echo "→ Upgrading pip/setuptools/wheel"
"$VENV/bin/python" -m pip install -q --upgrade pip setuptools wheel

echo "→ Installing PyObjC (requirements.txt)"
"$VENV/bin/python" -m pip install -q -r "$ROOT/requirements.txt"

echo "→ Installing ctimeli (editable)"
"$VENV/bin/python" -m pip install -q -e "$ROOT"

cp -n "$ROOT/.env.example" "$ROOT/.env"
echo "→ Env: $ROOT/.env"

_patch_python_calendar_usage() {
  local plist
  plist="$("$VENV/bin/python" -c 'from ctimeli.adapters.macos.python_plist import python_framework_info_plist; print(python_framework_info_plist())')"
  if "$VENV/bin/python" -c 'from ctimeli.adapters.macos.python_plist import calendar_usage_description_present; raise SystemExit(0 if calendar_usage_description_present() else 1)'; then
    echo "→ Python Calendar usage description: already present"
    return 0
  fi
  echo "→ One-time patch: Python needs NSCalendarsFullAccessUsageDescription"
  echo "  so macOS can show the Calendar Allow dialog (may ask for your password)."
  if sudo /usr/libexec/PlistBuddy -c "Add :NSCalendarsFullAccessUsageDescription string 'CtimeLI reads your calendar to auto-start timers before meetings.'" "$plist"; then
    echo "→ Python Calendar usage description: added"
  elif osascript - "$plist" <<'OSA'
on run argv
  set plistPath to item 1 of argv
  set plistCommand to "Add :NSCalendarsFullAccessUsageDescription string 'CtimeLI reads your calendar to auto-start timers before meetings.'"
  do shell script "/usr/libexec/PlistBuddy -c " & quoted form of plistCommand & " " & quoted form of plistPath with administrator privileges
end run
OSA
  then
    echo "→ Python Calendar usage description: added (via macOS admin dialog)"
  else
    echo "→ Skipped plist patch — run ./run permissions after fixing manually." >&2
  fi
}
_patch_python_calendar_usage

echo "→ Permissions (optional — ./run permissions to redo later)"
echo "  Timers work without these; they unlock block-end tidy + calendar auto-start."
"$VENV/bin/python" -m ctimeli permissions || true

echo "Installed. Try: $ROOT/run watch"
echo "Watch runs in the menu bar — you can close the terminal after it starts."

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
