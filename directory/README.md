# wbauth directory backend

Production: https://wbauth.silov801.workers.dev

Phase 3 production directory: a Hono + Cloudflare Workers + D1 backend that
serves the `draft-meunier-http-message-signatures-directory-05` JWKS surface
and accepts proof-of-key-ownership registrations (D-38).

## Routes

| Method | Path                                                        | Purpose                                                                  |
| ------ | ----------------------------------------------------------- | ------------------------------------------------------------------------ |
| POST   | `/register/challenge`                                       | Request a 5-min nonce for proof-of-key-ownership.                        |
| POST   | `/register/submit`                                          | Submit the signed Signature Agent Card (RFC 9421-signed by the kid).    |
| GET    | `/.well-known/http-message-signatures-directory`            | Directory's own signed JWKS (1 key) per Open Question #1.                |
| GET    | `/.well-known/http-message-signatures-directory/{kid}`      | Agent JWKS, signed by the directory's key.                               |
| GET    | `/agents/{kid}`                                             | Full Signature Agent Card (unsigned JSON, `max-age=60`).                 |
| GET    | `/agents?page=N`                                            | Paginated list (50/page).                                                |
| GET    | `/agents?all=true`                                          | Full list (up to 10000) — fallback for snapshot consumers.               |
| GET    | `/static/all.json`                                          | Full snapshot — Plan 03-02's nightly Action consumes this.               |
| GET    | `/healthz`                                                  | `{ok:true}`. Good for uptime checks.                                    |

## Layout

```
directory/
├── wrangler.jsonc               # Worker config (name=wbauth, D1 binding, observability)
├── migrations/
│   ├── 0001_create_agents.sql              # D-36 schema
│   ├── 0002_create_registration_challenges.sql
│   └── 0003_create_ratelimit.sql
├── src/
│   ├── index.ts                 # Hono entry; mounts routers + onError
│   ├── env.ts                   # Bindings type
│   ├── blocklist.ts             # D-43 reserved-name guard
│   ├── ratelimit.ts             # D-40+D-48 D1 small-row strategy
│   ├── signing.ts               # Lazy directory signer init
│   ├── schemas.ts               # zod schemas for register bodies
│   └── routes/
│       ├── register.ts          # /register/challenge + /register/submit
│       └── read.ts              # /.well-known/..., /agents, /static/all.json
└── tests/
    ├── handlers.test.ts         # End-to-end handler tests via SELF.fetch
    ├── blocklist.test.ts        # Includes 'googlestyle-app' false-positive guard
    ├── ratelimit.test.ts        # 11th call → 429; cleanup-on-write
    └── verify.test.ts           # web-bot-auth happy + tampered-sig rejection
```

## Secrets

`DIRECTORY_PRIVATE_JWK` — Ed25519 JWK (`{kty,crv,kid,d,x}` JSON-stringified).
Stored as a Cloudflare Worker secret, NEVER committed.

The kid in the secret IS the directory's published kid: external verifiers
fetch `https://wbauth.silov801.workers.dev/.well-known/http-message-signatures-directory`
to discover it.

### Rotation procedure (D-56)

The directory key is the cryptographic root of every signed read response. If
compromised, verifiers cannot trust ANY response from this Worker until a new
key is published. Rotate immediately on suspected compromise; otherwise leave
in place — rotation forces every verifier to refresh its cached directory JWKS.

1. **Generate a new JWK locally** (in a private terminal, no screen sharing):
   ```bash
   cd <repo-root>
   uv run python python/scripts/generate_directory_jwk.py
   # The single line of JSON on stdout IS the new secret value.
   # The kid is also printed to stderr for reference.
   ```

2. **Provision the new value as a Worker secret** (overwrites existing):
   ```bash
   cd directory
   npx wrangler secret put DIRECTORY_PRIVATE_JWK
   # Paste the JSON line from step 1 when prompted; press Enter.
   ```
   Wrangler prints `Success! Uploaded secret DIRECTORY_PRIVATE_JWK`.

3. **Verify the new directory kid is live:**
   ```bash
   curl -s https://wbauth.silov801.workers.dev/.well-known/http-message-signatures-directory \
     | python3 -c "import json,sys; print(json.loads(sys.stdin.read())['keys'][0]['kid'])"
   ```

4. **Notify verifiers** (out-of-band) that the directory kid has changed.
   Per spec, verifiers re-fetch the directory's own JWKS to discover the new
   kid. In-flight verifications using the previous kid will fail until each
   verifier refreshes its cache (typically within the 5-minute `max-age`).

There is intentionally no overlap window for the directory's own key —
it's a single signing identity, not a multi-key bundle. If you need a
zero-downtime rotation procedure, that's a post-v1 enhancement.

## D1

Database: `wbauth-directory` (binding `DB`).

Migrations live under `migrations/` and are wrangler-managed (D-55).

```bash
# Apply to local miniflare for dev:
npm run -w directory migrate:local

# Apply to production:
npm run -w directory migrate:remote
```

## Pitfalls honored

- Cache-Control on `/.well-known/.../{kid}` is `public, max-age=300` — NO
  `immutable` (Pitfall 1 + Open Question #4: the JWKS document at a kid
  CAN change with multi-key rotation).
- Rate-limit cleanup runs inside the same `.batch([...])` as the check
  (Pitfall 4 — prevents the table from growing forever).
- `app.onError` returns generic `{error:"internal"}` 500 (V7 ASVS — never
  leak stack traces to clients; details go to `wrangler tail`).
- Nonce DELETE happens BEFORE the 201 response (T-03-02 replay regression
  guard — tested in `handlers.test.ts`).
