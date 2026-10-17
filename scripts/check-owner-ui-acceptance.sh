#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MARKER="${EZB_OWNER_ACCEPTANCE_MARKER:-OWNER-UI-ACCEPTED}"

COMPOSE_FILE="${EZB_COMPOSE_FILE:-$ROOT/.devcontainer/docker-compose.yml}"
WP_CMD=(docker compose -f "$COMPOSE_FILE" run --rm --entrypoint wp bootstrap)

ID="$("${WP_CMD[@]}" post list \
  --post_type=ezb_project \
  --name=owner-editability-test \
  --post_status=draft \
  --field=ID \
  --allow-root | head -1)"

if [[ -z "$ID" ]]; then
  echo "OWNER_UI_ACCEPTANCE_NOT_READY: draft owner-editability-test not found" >&2
  exit 2
fi

STATUS="$("${WP_CMD[@]}" post get "$ID" --field=post_status --allow-root)"
TITLE="$("${WP_CMD[@]}" post get "$ID" --field=post_title --allow-root)"
CONTENT="$("${WP_CMD[@]}" post get "$ID" --field=post_content --allow-root)"

if [[ "$STATUS" != "draft" ]]; then
  echo "OWNER_UI_ACCEPTANCE_FAIL: acceptance Project must remain draft" >&2
  exit 3
fi

if [[ "$TITLE" != *"$MARKER"* && "$CONTENT" != *"$MARKER"* ]]; then
  echo "OWNER_UI_ACCEPTANCE_PENDING: marker '$MARKER' not found in the draft title or content" >&2
  exit 4
fi

echo "EZB_OWNER_UI_ACCEPTANCE_PASS"
echo "post_id=$ID"
echo "post_status=$STATUS"
echo "marker=$MARKER"
