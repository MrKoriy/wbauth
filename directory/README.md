# directory/

Phase 1: Hello-world Cloudflare Worker validating the Day-1 hosting test (D-04).

Phase 3 will replace `src/index.ts` with the real JWKS directory backend
(per D-02: TypeScript on Cloudflare Workers + D1, zero billing).

## Commands

- `pnpm dev` — local dev server (`wrangler dev`)
- `pnpm deploy` — deploy to `*.workers.dev`

## D1 Database

Database name: `wbauth-day1-test`
See `wrangler.jsonc` for the bound `database_id`.
