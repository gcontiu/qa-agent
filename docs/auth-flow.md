# Auth Flow — curl & Postman

All qa-agent API endpoints (except `/health` and `/auth/config`) require a Supabase JWT:

```
Authorization: Bearer <access_token>
```

---

## Prerequisites

You need two public values from your Supabase project  
(**Settings → API → Project URL** and **anon/public key**):

```
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_ANON_KEY=eyJ...
```

---

## 1. Sign up (create account)

```bash
curl -sX POST "$SUPABASE_URL/auth/v1/signup" \
  -H "apikey: $SUPABASE_ANON_KEY" \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"your-password"}'
```

**Response:** `200` with user object.

> **Email confirmation** — by default Supabase sends a confirmation email.
> For local / staging testing, disable it:  
> Supabase Dashboard → **Authentication → Providers → Email → disable "Confirm email"**.  
> With confirmation disabled, sign-up returns a full session immediately.

---

## 2. Sign in (get access token)

```bash
TOKEN=$(curl -sX POST "$SUPABASE_URL/auth/v1/token?grant_type=password" \
  -H "apikey: $SUPABASE_ANON_KEY" \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"your-password"}' \
  | jq -r '.access_token')

echo $TOKEN
```

The `access_token` is a signed JWT valid for 1 hour. Use it as the Bearer token in all requests.

---

## 3. Call the qa-agent API

```bash
QA_API=https://qa-agent-sp.fly.dev   # or http://localhost:8080

# List products
curl -s "$QA_API/products" \
  -H "Authorization: Bearer $TOKEN" | jq .

# Create a product
curl -sX POST "$QA_API/products" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"My App","url":"https://myapp.example.com"}'

# Start a QA run
curl -sX POST "$QA_API/runs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"product_id":"<product-uuid>"}'

# Poll run status
curl -s "$QA_API/runs/<run-id>" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

---

## 4. Postman setup

1. Create a new collection.
2. **Authorization tab** → Type: `Bearer Token` → Token: `{{access_token}}`
3. Add a collection variable `access_token`.
4. Add a **Pre-request Script** on the collection (or a dedicated "Login" request):

```javascript
// Run once — stores token as collection variable
pm.sendRequest({
  url: pm.environment.get('SUPABASE_URL') + '/auth/v1/token?grant_type=password',
  method: 'POST',
  header: {
    'apikey': pm.environment.get('SUPABASE_ANON_KEY'),
    'Content-Type': 'application/json',
  },
  body: {
    mode: 'raw',
    raw: JSON.stringify({
      email: pm.environment.get('EMAIL'),
      password: pm.environment.get('PASSWORD'),
    }),
  },
}, (err, res) => {
  pm.collectionVariables.set('access_token', res.json().access_token)
})
```

5. Add environment variables: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `EMAIL`, `PASSWORD`.

---

## 5. Local dev (no Supabase configured)

When `SUPABASE_JWT_SECRET` is **not** set, the server returns a dev user for every request — no token needed.

```bash
curl http://localhost:8080/products   # works without Authorization header
```

This mode is symmetric with `DATABASE_URL` absent (DB operations are no-ops).

---

## Token lifetime & refresh

| Property | Value |
|---|---|
| Lifetime | 1 hour (Supabase default) |
| Algorithm | HS256 |
| Audience | `authenticated` |
| Refresh | `POST /auth/v1/token?grant_type=refresh_token` with `refresh_token` |

Tokens are verified locally (no network call). A revoked session remains valid until it expires — acceptable for MVP. See `src/qa_agent/auth.py` for implementation.
