#!/usr/bin/env bash
# Phase 3 DIR-05 + D-45 + D-46: nightly directory snapshot.
#
# Invoked by .github/workflows/snapshot.yml (cron disabled in Phase 3 per
# Open Question #3 / Pitfall 7; Phase 5 enables once GitHub remote / D-08
# resolves). Available manually via:
#   gh workflow run nightly-directory-snapshot
#
# Env vars (with defaults):
#   DIRECTORY_URL — defaults to https://wbauth.silov801.workers.dev (D-49)
#   OUT_DIR       — defaults to ./snapshot-build/snapshots
#
# Output:
#   $OUT_DIR/directory-snapshot-YYYY-MM-DD.json — dated snapshot
#   $OUT_DIR/latest.json                        — copy of today's
#   Files older than 30 days under $OUT_DIR are pruned (D-46).
set -euo pipefail

DIRECTORY_URL="${DIRECTORY_URL:-https://wbauth.silov801.workers.dev}"
OUT_DIR="${OUT_DIR:-./snapshot-build/snapshots}"

mkdir -p "$OUT_DIR"
DATE=$(date -u +%Y-%m-%d)
DEST="${OUT_DIR}/directory-snapshot-${DATE}.json"

# /static/all.json is keyset-paginated (1000/page): follow next_cursor and
# merge every page into one {generated_at, count, agents} document.
echo "Fetching ${DIRECTORY_URL}/static/all.json (all pages) -> ${DEST}"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
CURSOR=""
PAGE=0
while :; do
  URL="${DIRECTORY_URL}/static/all.json"
  [ -n "$CURSOR" ] && URL="${URL}?cursor=${CURSOR}"
  curl --fail --silent --show-error --location "$URL" -o "${TMP}/page-$(printf %05d "$PAGE").json"
  CURSOR=$(jq -r '.next_cursor // empty' "${TMP}/page-$(printf %05d "$PAGE").json")
  PAGE=$((PAGE + 1))
  [ -z "$CURSOR" ] && break
  [ "$PAGE" -ge 10000 ] && { echo "too many pages" >&2; exit 1; }
done
jq -s '{generated_at: (.[0].generated_at), count: (map(.agents | length) | add), agents: (map(.agents) | add)}' \
  "${TMP}"/page-*.json > "${DEST}"

cp "${DEST}" "${OUT_DIR}/latest.json"

# D-46: 30-day retention. -mtime +30 prunes files older than 30 days.
# `|| true` keeps the script green if there's nothing to delete (fresh repo).
echo "Pruning snapshots older than 30 days under ${OUT_DIR}"
find "${OUT_DIR}" -name 'directory-snapshot-*.json' -mtime +30 -delete || true

ls -la "${OUT_DIR}"
