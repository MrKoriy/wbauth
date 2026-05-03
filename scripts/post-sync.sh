#!/usr/bin/env bash
# scripts/post-sync.sh
#
# Workaround for uv issue: editable installs of workspace-member packages
# are written with the macOS UF_HIDDEN file flag set, which causes Python
# 3.13+ to silently skip them per CPython security policy (GH-99458).
#
# Symptom without this script: `import wbauth` fails after `uv sync` even
# though `wbauth-0.1.0.dist-info` is present in `.venv/lib/.../site-packages/`.
# Verify with `python -v -c pass 2>&1 | grep wbauth` — you'll see
# "Skipping hidden .pth file: '..._editable_impl_wbauth.pth'".
#
# This script clears UF_HIDDEN from any `.pth` file in the workspace venv
# whose name starts with `_editable_impl_`. Idempotent; safe to re-run.
#
# Usage:
#   scripts/post-sync.sh                # operates on ./.venv
#   VENV=/path/to/venv scripts/post-sync.sh
#
# Always run after `uv sync`. Not needed after `pip install` (pip doesn't set the flag).
set -euo pipefail
VENV="${VENV:-.venv}"
if [[ "$(uname -s)" != "Darwin" ]]; then
  exit 0  # macOS-only quirk; no-op on Linux/Windows
fi
if [[ ! -d "$VENV" ]]; then
  echo "post-sync: $VENV not found, nothing to do" >&2
  exit 0
fi
PTH_DIR="$(find "$VENV/lib" -type d -name 'site-packages' | head -1)"
if [[ -z "${PTH_DIR:-}" ]]; then
  echo "post-sync: no site-packages dir under $VENV/lib" >&2
  exit 0
fi
shopt -s nullglob
fixed=0

# 1) Editable-install .pth files (the original symptom — wbauth import fails).
for pth in "$PTH_DIR"/_editable_impl_*.pth; do
  if ls -lO "$pth" | grep -q hidden; then
    chflags nohidden "$pth"
    echo "post-sync: cleared UF_HIDDEN on $(basename "$pth")"
    fixed=$((fixed + 1))
  fi
done

# 2) Package directories themselves AND their contents. Plan 03 discovery:
# uv 0.11.7 sets UF_HIDDEN on every file/dir it writes during a sync — not
# just `.pth` files. When the package dir is hidden, Python's importer
# treats it as a namespace package (NamespaceLoader instead of regular
# package), so `from _pytest import __version__` fails with
# `ImportError: cannot import name '__version__' from '_pytest' (unknown location)`.
# Even when the top-level dir is un-hidden, the children (sub-packages,
# .py files) remain hidden and Python skips them.
#
# Fix: recursively un-hide the entire site-packages tree. Idempotent
# (chflags nohidden on a non-hidden entry is a no-op).
hidden_count=$(find "$PTH_DIR" -flags +hidden 2>/dev/null | wc -l | tr -d ' ')
if [[ "${hidden_count:-0}" -gt 0 ]]; then
  # Process in batches; site-packages can have thousands of files.
  find "$PTH_DIR" -flags +hidden -print0 2>/dev/null \
    | xargs -0 chflags nohidden 2>/dev/null || true
  echo "post-sync: cleared UF_HIDDEN on $hidden_count site-packages entries (recursive)"
  fixed=$((fixed + hidden_count))
fi

if [[ $fixed -eq 0 ]]; then
  echo "post-sync: no hidden site-packages entries found (already clean or non-uv install)"
fi
