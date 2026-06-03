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

# supabase db query writes "Initialising login role..." and version warnings to stdout,
# mixed with the JSON payload. Extract only the JSON object from the output.
_db_query() {
  supabase db query "$1" --linked 2>/dev/null \
    | python3 -c "
import sys, json, re
text = sys.stdin.read()
m = re.search(r'\{.*\}', text, re.DOTALL)
if m:
    print(m.group())
"
}

_json_field() {
  # _json_field <json> <key>
  python3 -c "import sys,json; d=json.loads(sys.argv[1]); rows=d.get('rows',[]); print(rows[0].get(sys.argv[2],'') if rows else '')" "$1" "$2" 2>/dev/null || true
}

echo "==> Looking up user: $EMAIL"
RESULT=$(_db_query "SELECT id FROM public.users WHERE email = '${EMAIL}';")
USER_ID=$(_json_field "$RESULT" "id")

if [[ -z "$USER_ID" ]]; then
  echo "Error: user '$EMAIL' not found in DB." >&2
  exit 1
fi

echo "    user_id: $USER_ID"

echo "==> Counting records to delete..."
COUNTS=$(_db_query "
SELECT
  (SELECT COUNT(*) FROM jobs     WHERE user_id   = '${USER_ID}') AS runs,
  (SELECT COUNT(*) FROM products WHERE user_id   = '${USER_ID}') AS products,
  (SELECT COUNT(*) FROM specs    WHERE product_id IN (SELECT id FROM products WHERE user_id = '${USER_ID}')) AS specs,
  (SELECT COUNT(*) FROM issues   WHERE product_id IN (SELECT id FROM products WHERE user_id = '${USER_ID}')) AS issues,
  (SELECT COUNT(*) FROM growth.drip_jobs       WHERE waitlist_id IN (SELECT id FROM growth.waitlist WHERE email = '${EMAIL}')) AS drip_jobs,
  (SELECT COUNT(*) FROM growth.beta_enrollments WHERE user_id    = '${USER_ID}') AS beta_enrollments,
  (SELECT COUNT(*) FROM growth.waitlist         WHERE email      = '${EMAIL}') AS waitlist;
")
python3 -c "
import sys, json
d = json.loads(sys.argv[1])
r = (d.get('rows') or [{}])[0]
print(f\"    runs={r.get('runs',0)}  products={r.get('products',0)}  specs={r.get('specs',0)}  issues={r.get('issues',0)}\")
print(f\"    waitlist={r.get('waitlist',0)}  beta_enrollments={r.get('beta_enrollments',0)}  drip_jobs={r.get('drip_jobs',0)}\")
" "$COUNTS"

echo "==> Deleting from DB..."
_db_query "
DELETE FROM jobs     WHERE user_id = '${USER_ID}';
DELETE FROM products WHERE user_id = '${USER_ID}';
DELETE FROM growth.drip_jobs        WHERE waitlist_id IN (SELECT id FROM growth.waitlist WHERE email = '${EMAIL}');
DELETE FROM growth.beta_enrollments WHERE user_id = '${USER_ID}';
DELETE FROM growth.waitlist         WHERE email = '${EMAIL}';
" > /dev/null
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
