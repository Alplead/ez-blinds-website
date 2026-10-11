#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${EZB_BASE_URL:-}"
ALLOW_HTTP="${EZB_ALLOW_HTTP:-0}"
TOKEN="${EZB_MAIL_PROBE_TOKEN:-EZB-MAIL-$(date -u +%Y%m%dT%H%M%SZ)-$$}"

if [[ -z "$BASE_URL" ]]; then
  echo "EZB_BASE_URL is required" >&2
  exit 2
fi

BASE_URL="${BASE_URL%/}"

if [[ "$BASE_URL" != https://* && "$ALLOW_HTTP" != "1" ]]; then
  echo "Mail delivery acceptance requires HTTPS unless EZB_ALLOW_HTTP=1 is explicitly set for development testing." >&2
  exit 3
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

CONTACT_URL="$BASE_URL/contact/"
POST_URL="$BASE_URL/wp-admin/admin-post.php"

curl -fsSL "$CONTACT_URL" -o "$TMP_DIR/contact.html"

NONCE="$(
  grep -o 'name="ezb_quote_nonce" value="[^"]*"' "$TMP_DIR/contact.html" \
    | sed -E 's/.*value="([^"]*)"/\1/' \
    | head -1
)"

if [[ -z "$NONCE" ]]; then
  echo "Could not extract ezb_quote_nonce from $CONTACT_URL" >&2
  exit 4
fi

HTTP_CODE="$(
  curl -sS \
    -o "$TMP_DIR/submit-body.html" \
    -D "$TMP_DIR/submit-headers.txt" \
    -w '%{http_code}' \
    -X POST "$POST_URL" \
    --data-urlencode 'action=ezb_quote' \
    --data-urlencode "ezb_quote_nonce=$NONCE" \
    --data-urlencode 'name=EZB Staging Mail Probe' \
    --data-urlencode 'email=probe@example.com' \
    --data-urlencode 'suburb=Staging acceptance' \
    --data-urlencode 'product=Other / Not sure' \
    --data-urlencode "message=External mail delivery acceptance token: $TOKEN"
)"

if [[ "$HTTP_CODE" != "302" ]]; then
  echo "Expected HTTP 302 from quote submission, got $HTTP_CODE" >&2
  exit 5
fi

if ! grep -qi 'location: .*quote_status=sent' "$TMP_DIR/submit-headers.txt"; then
  echo "Quote submission did not report quote_status=sent" >&2
  cat "$TMP_DIR/submit-headers.txt" >&2
  exit 6
fi

echo "EZB_MAIL_PROBE_SUBMISSION_PASS"
echo "token=$TOKEN"
echo "submitted_to=$POST_URL"
echo "MAILBOX_CONFIRMATION_REQUIRED"
echo "Acceptance is NOT complete until the intended mailbox receives a message containing the exact token above."
