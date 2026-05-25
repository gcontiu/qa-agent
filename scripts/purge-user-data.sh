#!/usr/bin/env bash
# Usage: ./scripts/purge-user-data.sh <email>
# Deletes all runs, products (+ specs, issues) for the given user from DB and Fly volume.

set -euo pipefail

EMAIL="${1:-}"
FLY_APP="qa-agent-sp"

if [[ -z "$EMAIL" ]]; then
  echo "Usage: $0 <email>" >&2
  exit 1
fi

echo "==> Looking up user: $EMAIL"
RESULT=$(supabase db query "SELECT id FROM public.users WHERE email = '${EMAIL}';" --linked 2>/dev/null)
USER_ID=$(echo "$RESULT" | python3 -c "import sys,json; rows=json.load(sys.stdin).get('rows',[]); print(rows[0]['id'] if rows else '')" 2>/dev/null || true)

if [[ -z "$USER_ID" ]]; then
  echo "Error: user '$EMAIL' not found in DB." >&2
  exit 1
fi

echo "    user_id: $USER_ID"

echo "==> Counting records to delete..."
COUNTS=$(supabase db query "
SELECT
  (SELECT COUNT(*) FROM jobs     WHERE user_id   = '${USER_ID}') AS runs,
  (SELECT COUNT(*) FROM products WHERE user_id   = '${USER_ID}') AS products,
  (SELECT COUNT(*) FROM specs    WHERE product_id IN (SELECT id FROM products WHERE user_id = '${USER_ID}')) AS specs,
  (SELECT COUNT(*) FROM issues   WHERE product_id IN (SELECT id FROM products WHERE user_id = '${USER_ID}')) AS issues;
" --linked 2>/dev/null)

python3 -c "
import sys, json
rows = json.loads('''${COUNTS}''').get('rows', [{}])
r = rows[0] if rows else {}
print(f\"    runs={r.get('runs',0)}  products={r.get('products',0)}  specs={r.get('specs',0)}  issues={r.get('issues',0)}\")
" 2>/dev/null || echo "$COUNTS"

echo "==> Deleting from DB..."
supabase db query "
DELETE FROM jobs     WHERE user_id = '${USER_ID}';
DELETE FROM products WHERE user_id = '${USER_ID}';
" --linked 2>/dev/null
echo "    DB: done."

echo "==> Deleting run files from Fly volume ($FLY_APP)..."
fly ssh console -a "$FLY_APP" -C "
  count=0
  for f in \$(grep -rl '\"user_id\": \"${USER_ID}\"' /app/reports/run-*/run_status.json 2>/dev/null); do
    dir=\"\$(dirname \"\$f\")\"
    rm -rf \"\$dir\"
    count=\$((count + 1))
  done
  echo \"    volume: removed \$count run director\$([ \$count -eq 1 ] && echo y || echo ies).\"
" 2>/dev/null || echo "    volume: ssh failed or no files found."

echo "==> Done."
