# Day-1 Hosting Confirmation Result (DIR-06)

**Date:** 2026-05-03
**STATUS: PASS**

## Cloudflare Account
- Email: silov801@gmail.com
- Account ID: 2a1e5d83dbc5d553a3537d7a79009899
- No credit card on file (Workers Free + D1 free tier)
- Authentication: OAuth token via `npx wrangler login`

## Worker
- Name: wbauth-day1-test
- URL: https://wbauth-day1-test.silov801.workers.dev
- Compatibility date: 2026-05-01
- Version ID at first deploy: 41b390fb-70b0-4b96-8943-b67d2f203791
- GET / returns: "Day 1 hello-world" (HTTP 200)
- GET /ping returns: {"ok":true,"row_count":1} (HTTP 200)

## D1 Database
- Name: wbauth-day1-test
- database_id: 13e5aebd-4999-4333-9a23-7fd7fb75549a
- Region: EEUR (served by FRA colo, v3-prod)
- Table `hello` row count at deploy time: 1
- Seeded message: "Day 1 works"

## Locked Decisions Validated
- **D-01 (zero billing):** confirmed — no credit card was required at signup or for Workers/D1 provisioning
- **D-02 (TypeScript on Workers + D1):** confirmed — `wrangler deploy` and `wrangler d1 execute --remote` both succeed; the deployed Worker reads from the D1 binding via `env.DB.prepare(...)` end-to-end
- **D-03 (no custom domain):** confirmed — using Cloudflare-assigned `*.workers.dev` URL (`silov801.workers.dev` subdomain)
- **D-04 (Cloudflare-only protocol):** satisfied — no fallback to Fly.io / Railway needed; signup, OAuth, deploy, and D1 round-trip all worked from the developer's IP without VPN

## Wrangler Tooling
- Wrangler version: 4.87.0
- Installed locally to `directory/node_modules/wrangler` (via `npm install` — `pnpm` not present on the dev machine; Plan 02 will hoist into the workspace lockfile)
- Bound D1 namespace name in code: `DB` (matches plan template, NOT auto-suggested `wbauth_day1_test`)

## Environment Notes
- Node version: v22.22.2
- npm version: 10.9.7
- Operating system: Darwin 25.4.0 (macOS)
- pnpm: NOT installed (planner expected pnpm; `npm install` used instead, which produced a local `package-lock.json` rather than `pnpm-lock.yaml`. Plan 02 monorepo scaffold should reconcile this — either install pnpm system-wide or accept npm and update D-10 / Plan 02 accordingly.)

## Next Steps
- Phase 1 unblocked. Plan 02 (monorepo scaffold) and downstream plans 03 / 04 may proceed in Wave 2+.
- The `directory/` workspace member contains throwaway code; Phase 3 will replace `src/index.ts` with the real JWKS backend.
- Plan 02 should: (a) add a root-level `pnpm-workspace.yaml` (or alternative if pnpm install is deferred) that includes `directory/`, (b) decide whether to swap `directory/package-lock.json` for `pnpm-lock.yaml`, (c) add a root `.gitignore` covering `node_modules/`, `.wrangler/`, `dist/`.
