---
phase: 01-foundation-cryptographic-root
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - directory/wrangler.jsonc
  - directory/schema.sql
  - directory/src/index.ts
  - directory/package.json
  - directory/README.md
  - .planning/phases/01-foundation-cryptographic-root/01-01-HOSTING-RESULT.md
autonomous: false
requirements: [DIR-06]
user_setup:
  - service: cloudflare
    why: "Day-1 hosting confirmation — Workers + D1 free tier (D-04). The whole Phase 1 is unblocked by this; if signup fails, the entire zero-billing architecture (D-01, D-02) must be revisited."
    env_vars: []
    dashboard_config:
      - task: "Sign up for Cloudflare account"
        location: "https://dash.cloudflare.com/sign-up"
      - task: "Authenticate wrangler CLI via OAuth (`npx wrangler login` opens browser)"
        location: "Local terminal → browser → dash.cloudflare.com OAuth consent"
      - task: "Verify Workers Free + D1 free tier are enabled (no credit card required per RESEARCH.md §1)"
        location: "https://dash.cloudflare.com/ → Workers & Pages, D1"

must_haves:
  truths:
    - "Cloudflare account exists and `wrangler whoami` returns the user's email"
    - "A hello-world Worker is deployed at a `*.workers.dev` URL and responds 200 to GET /"
    - "A D1 database named `wbauth-day1-test` exists and the Worker can read from it"
    - "GET /ping on the deployed Worker returns `{\"ok\": true, \"row_count\": 1}`"
    - "The `wrangler d1 execute wbauth-day1-test --remote --command='SELECT * FROM hello'` returns at least one row"
  artifacts:
    - path: directory/wrangler.jsonc
      provides: "Cloudflare Worker config with D1 binding"
      contains: "d1_databases"
    - path: directory/schema.sql
      provides: "D1 schema for the hello table"
      contains: "CREATE TABLE"
    - path: directory/src/index.ts
      provides: "Hello-world Worker fetch handler with /ping route reading from D1"
      contains: "env.DB.prepare"
    - path: directory/package.json
      provides: "Local wrangler devDependency"
      contains: "wrangler"
    - path: .planning/phases/01-foundation-cryptographic-root/01-01-HOSTING-RESULT.md
      provides: "Recorded result of the hosting confirmation: deployed URL, D1 database id, pass/fail status"
      contains: "STATUS: PASS"
  key_links:
    - from: "directory/src/index.ts"
      to: "Cloudflare D1 (DB binding)"
      via: "env.DB.prepare(...).all() in fetch handler"
      pattern: "env\\.DB\\.prepare"
    - from: "directory/wrangler.jsonc"
      to: "directory/src/index.ts"
      via: "main entry point reference"
      pattern: "\"main\":\\s*\"src/index\\.ts\""
    - from: "directory/wrangler.jsonc"
      to: "the live D1 database"
      via: "database_id binding"
      pattern: "database_id"
---

<objective>
Confirm — before a single line of cryptographic code is written — that the Cloudflare Workers + D1 hosting platform works end-to-end with the developer's account and network.

Purpose: This is the SINGLE strict serial blocker for the entire project. The zero-billing architecture (D-01) and TypeScript-on-Workers directory backend (D-02) are LOCKED user decisions. If Cloudflare signup fails or `wrangler login` cannot reach the dashboard from the developer's IP, the planner ASSUMPTIONS A1 and A2 in 01-RESEARCH.md are invalidated and the user MUST be escalated per D-04 BEFORE any other Phase 1 work begins. There is NO automatic fallback to Fly.io / Railway — those paths were eliminated by D-01.

Output: A deployed `*.workers.dev` URL serving a hello-world handler that reads from a D1 database, plus a recorded result file documenting the URL, D1 database id, and PASS/FAIL status. The `directory/` workspace member exists with throwaway code that Phase 3 will replace.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/01-foundation-cryptographic-root/01-CONTEXT.md
@.planning/phases/01-foundation-cryptographic-root/01-RESEARCH.md

<interfaces>
<!-- Concrete file contents the executor will create. No exploration needed. -->

From 01-RESEARCH.md §1, Templates section (these are CANONICAL — copy verbatim, then fill in `<paste-from-d1-create-output>`):

`directory/wrangler.jsonc` template:
```jsonc
{
  "name": "wbauth-day1-test",
  "main": "src/index.ts",
  "compatibility_date": "2026-05-01",
  "d1_databases": [
    {
      "binding": "DB",
      "database_name": "wbauth-day1-test",
      "database_id": "<paste-from-d1-create-output>"
    }
  ]
}
```

`directory/schema.sql` template:
```sql
CREATE TABLE IF NOT EXISTS hello (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  message TEXT NOT NULL,
  created_at INTEGER NOT NULL DEFAULT (unixepoch())
);
INSERT INTO hello (message) VALUES ('Day 1 works');
```

`directory/src/index.ts` template:
```typescript
export interface Env {
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === "/ping") {
      const { results } = await env.DB.prepare(
        "SELECT COUNT(*) as count FROM hello"
      ).all<{ count: number }>();
      return Response.json({ ok: true, row_count: results[0].count });
    }
    return new Response("Day 1 hello-world", { status: 200 });
  },
};
```

`directory/package.json` template (minimal — Plan 02 will integrate it into the pnpm workspace):
```json
{
  "name": "wbauth-directory",
  "version": "0.0.1",
  "private": true,
  "type": "module",
  "scripts": {
    "deploy": "wrangler deploy",
    "dev": "wrangler dev"
  },
  "devDependencies": {
    "wrangler": "^4.87.0"
  }
}
```

Wrangler command sequence (verified against 4.87.0 in 01-RESEARCH.md §1):
- `npx wrangler login` — interactive browser auth
- `npx wrangler whoami` — confirm logged in
- `npx wrangler d1 create wbauth-day1-test` — emits `database_id` to paste into wrangler.jsonc
- `npx wrangler d1 execute wbauth-day1-test --remote --file=./schema.sql` — apply schema to remote D1
- `npx wrangler deploy` — deploys, prints `https://wbauth-day1-test.<subdomain>.workers.dev`
- `npx wrangler d1 execute wbauth-day1-test --remote --command="SELECT * FROM hello"` — confirm row exists

Failure escalation table from 01-RESEARCH.md §1:
| Failure | Likely Cause | Escalate? |
| `wrangler login` doesn't open browser, or browser hangs at dash.cloudflare.com | RU IP block on dashboard | YES — try a VPN; if still fails, escalate to user |
| Account creation requires payment method | Region-specific signup flow | YES — escalate, do not add a card |
| `wrangler d1 create` returns "subscription required" | Region-specific behavior | YES — escalate |
</interfaces>
</context>

<tasks>

<task type="checkpoint:human-action" gate="blocking">
  <name>Task 1: Cloudflare account signup + wrangler login (HUMAN-ONLY: dashboard OAuth)</name>
  <read_first>
    - .planning/phases/01-foundation-cryptographic-root/01-CONTEXT.md (D-01, D-02, D-04 — locked decisions)
    - .planning/phases/01-foundation-cryptographic-root/01-RESEARCH.md §1 "Day-1 Hosting Test Procedure" (full section)
    - .planning/phases/01-foundation-cryptographic-root/01-RESEARCH.md §1 "Failure Modes & Escalation" subtable
  </read_first>
  <what-built>
    Account creation and OAuth authentication are HUMAN-ONLY actions (browser-based dashboard signup + OAuth consent screen). Claude has prepared no automation in this task — it pauses here so the user performs the signup BEFORE any wrangler commands are attempted. This implements D-04 ("Day-1 hosting protocol = Cloudflare-only. ... If Cloudflare rejects the signup or the available payment card for any reason, escalate to user before proceeding.").
  </what-built>
  <how-to-verify>
    User actions (perform in order, report results back to Claude):

    1. Open https://dash.cloudflare.com/sign-up in a browser. Sign up with email + password. Verify email if required.

    2. After landing in the dashboard, confirm the **Workers & Pages** section is accessible (left sidebar). The free plan should be active by default — NO credit card prompt should appear at signup. If a credit card is required at signup, STOP and report back: this invalidates D-04's assumption A1.

    3. In a terminal at the repo root:
       ```bash
       cd directory  # (will be created by Task 2 if missing)
       mkdir -p directory && cd directory
       pnpm init  # if package.json not present yet
       pnpm add -D wrangler@latest
       npx wrangler whoami  # may say "not logged in"
       npx wrangler login   # opens browser
       ```

    4. The browser should open to a Cloudflare consent page ("Allow Wrangler to access your Cloudflare account"). Click Allow.
       - **If the browser hangs at dash.cloudflare.com or never loads:** this is the RU-IP-geoblock failure mode flagged in RESEARCH.md §1. STOP and report. Mitigation: try a VPN; if still failing, generate an API token in the dashboard via VPN and set `CLOUDFLARE_API_TOKEN` env var.

    5. After consent, terminal should print `Successfully logged in.`

    6. Confirm: `npx wrangler whoami` should now print the email address used for signup.

    Expected outcomes (report each):
       - [ ] Account created without requiring a credit card
       - [ ] `wrangler login` flow completed (browser opened, consent granted)
       - [ ] `wrangler whoami` prints the signup email

    If ANY step fails, report the exact error message and STOP. Do not proceed to Task 2.
  </how-to-verify>
  <acceptance_criteria>
    - User reports back: "wrangler whoami returns &lt;email&gt;"  (paste the actual email/output)
    - No credit card was required at signup (per A1)
    - `npx wrangler login` succeeded without VPN, OR user explicitly chose to proceed via API token after a documented dashboard-unreachable failure
  </acceptance_criteria>
  <resume-signal>
    Type "logged in as &lt;email&gt;" once `wrangler whoami` succeeds. If signup or login failed, type "ESCALATE: &lt;exact failure&gt;" and Claude will halt the entire phase per D-04.
  </resume-signal>
</task>

<task type="auto">
  <name>Task 2: Scaffold directory/ workspace and provision D1 database</name>
  <read_first>
    - .planning/phases/01-foundation-cryptographic-root/01-RESEARCH.md §1 "Wrangler Commands" and "Templates" subsections (verbatim source for files)
    - .planning/phases/01-foundation-cryptographic-root/01-CONTEXT.md D-10 (monorepo layout — `directory/` is a pnpm workspace member; Phase 3 will replace src/index.ts)
    - 01-RESEARCH.md §"Recommended Project Structure" tree (confirms directory/ layout)
  </read_first>
  <action>
    Create the `directory/` workspace member with the four template files from `<interfaces>` above. Then provision the D1 database and wire it.

    Step-by-step:

    1. From repo root, create directory structure:
       ```bash
       mkdir -p directory/src
       ```

    2. Write `directory/package.json` with content from `<interfaces>` block above (minimal, name="wbauth-directory", wrangler ^4.87.0 as devDependency).

    3. Run `cd directory && pnpm install` to install wrangler locally (creates `directory/node_modules/` and `directory/pnpm-lock.yaml` — note: Plan 02 will hoist this into the workspace lockfile; for now a local lockfile is fine).

    4. Create the D1 database:
       ```bash
       npx wrangler d1 create wbauth-day1-test
       ```
       Capture the output — it includes a `database_id` (UUID-like string) and a binding stanza. Save this value.

    5. Write `directory/wrangler.jsonc` from the `<interfaces>` template, REPLACING `<paste-from-d1-create-output>` with the actual database_id captured in step 4.

    6. Write `directory/schema.sql` verbatim from the `<interfaces>` template (creates `hello` table, inserts one row).

    7. Apply schema to remote D1:
       ```bash
       npx wrangler d1 execute wbauth-day1-test --remote --file=./schema.sql
       ```
       Expected output: "Executed N commands ... successfully" (or similar). If errors, capture and stop.

    8. Write `directory/src/index.ts` verbatim from the `<interfaces>` template (the fetch handler with /ping route).

    9. Write `directory/README.md`:
       ```markdown
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
       ```

    DO NOT deploy yet — Task 3 deploys and verifies. This task only provisions filesystem state and the remote D1 database.
  </action>
  <verify>
    <automated>test -f directory/wrangler.jsonc &amp;&amp; test -f directory/schema.sql &amp;&amp; test -f directory/src/index.ts &amp;&amp; test -f directory/package.json &amp;&amp; grep -q '"main": "src/index.ts"' directory/wrangler.jsonc &amp;&amp; grep -q 'env.DB.prepare' directory/src/index.ts &amp;&amp; grep -q 'CREATE TABLE IF NOT EXISTS hello' directory/schema.sql &amp;&amp; ! grep -q '&lt;paste-from-d1-create-output&gt;' directory/wrangler.jsonc &amp;&amp; cd directory &amp;&amp; npx wrangler d1 execute wbauth-day1-test --remote --command='SELECT COUNT(*) as c FROM hello' | grep -q '"c": 1'</automated>
  </verify>
  <acceptance_criteria>
    - `directory/wrangler.jsonc` exists, contains `"main": "src/index.ts"`, and has a real database_id (not the `&lt;paste-from-d1-create-output&gt;` placeholder)
    - `directory/schema.sql` exists and contains `CREATE TABLE IF NOT EXISTS hello`
    - `directory/src/index.ts` exists and contains `env.DB.prepare` (proves the D1 binding is used)
    - `directory/package.json` exists with `wrangler` listed in devDependencies
    - `directory/README.md` exists explaining the Phase 1 vs Phase 3 boundary (per D-02)
    - The remote D1 database `wbauth-day1-test` has been provisioned and the `hello` table contains exactly 1 row (the seeded "Day 1 works" message)
  </acceptance_criteria>
  <done>
    `directory/` workspace skeleton exists with the four template files (filled with real database_id), the D1 database is provisioned, and the `hello` table has 1 row. Worker is NOT yet deployed — Task 3 handles that.
  </done>
</task>

<task type="auto">
  <name>Task 3: Deploy Worker and verify end-to-end (record result file)</name>
  <read_first>
    - directory/wrangler.jsonc (the file created in Task 2 — confirm database_id is filled)
    - directory/src/index.ts (the file created in Task 2 — confirm /ping route is present)
    - .planning/phases/01-foundation-cryptographic-root/01-RESEARCH.md §1 "Wrangler Commands" steps 7-9 (deploy + smoke-test commands)
    - .planning/phases/01-foundation-cryptographic-root/01-CONTEXT.md D-04 (escalate on failure, do not auto-fallback)
  </read_first>
  <action>
    Deploy the Worker and verify the full request → D1 → response loop. Then write a result file documenting the outcome.

    Step-by-step:

    1. From `directory/`, deploy:
       ```bash
       cd directory
       npx wrangler deploy
       ```
       Expected output line: `Deployed wbauth-day1-test to https://wbauth-day1-test.<subdomain>.workers.dev` (where `<subdomain>` is the user's auto-assigned Cloudflare subdomain). Capture the full URL.

    2. Smoke-test the deployed Worker:
       ```bash
       curl -s https://wbauth-day1-test.<subdomain>.workers.dev/
       # expect: "Day 1 hello-world"

       curl -s https://wbauth-day1-test.<subdomain>.workers.dev/ping
       # expect: {"ok":true,"row_count":1}
       ```

    3. Confirm D1 read from CLI side as a cross-check:
       ```bash
       npx wrangler d1 execute wbauth-day1-test --remote --command="SELECT * FROM hello"
       # expect: at least 1 row with message='Day 1 works'
       ```

    4. Write the result file at `.planning/phases/01-foundation-cryptographic-root/01-01-HOSTING-RESULT.md`:
       ```markdown
       # Day-1 Hosting Confirmation Result (DIR-06)

       **Date:** &lt;today's date YYYY-MM-DD&gt;
       **STATUS:** PASS

       ## Cloudflare Account
       - Email: &lt;email from wrangler whoami&gt;
       - No credit card on file (Workers Free + D1 free tier)

       ## Worker
       - Name: wbauth-day1-test
       - URL: https://wbauth-day1-test.&lt;subdomain&gt;.workers.dev
       - Compatibility date: 2026-05-01
       - GET / returns: "Day 1 hello-world"
       - GET /ping returns: {"ok":true,"row_count":1}

       ## D1 Database
       - Name: wbauth-day1-test
       - database_id: &lt;the UUID from wrangler d1 create&gt;
       - Table `hello` row count at deploy time: 1

       ## Locked Decisions Validated
       - D-01 (zero billing): confirmed — no card required
       - D-02 (TypeScript on Workers + D1): confirmed — wrangler deploy + D1 execute both work
       - D-03 (no custom domain): confirmed — using `*.workers.dev` URL
       - D-04 (Cloudflare-only protocol): satisfied — no fallback to Fly.io/Railway needed

       ## Next Steps
       - Phase 1 unblocked. Plan 02 (monorepo scaffold) and downstream plans may proceed.
       - The `directory/` workspace member contains throwaway code; Phase 3 will replace `src/index.ts` with the real JWKS backend.
       ```

    5. If ANY step fails (deploy errors, curl returns non-200, /ping returns row_count != 1), DO NOT write a PASS result file. Instead write the result file with `STATUS: FAIL` and the exact error output, and HALT the plan. The user must be re-engaged per D-04.
  </action>
  <verify>
    <automated>WORKER_URL=$(grep -E 'URL:.*workers\.dev' .planning/phases/01-foundation-cryptographic-root/01-01-HOSTING-RESULT.md | head -1 | awk '{print $NF}') &amp;&amp; test -n "$WORKER_URL" &amp;&amp; curl -sf "$WORKER_URL/" | grep -q "Day 1 hello-world" &amp;&amp; curl -sf "$WORKER_URL/ping" | grep -q '"ok":true' &amp;&amp; curl -sf "$WORKER_URL/ping" | grep -q '"row_count":1' &amp;&amp; grep -q "STATUS: PASS" .planning/phases/01-foundation-cryptographic-root/01-01-HOSTING-RESULT.md</automated>
  </verify>
  <acceptance_criteria>
    - `wrangler deploy` succeeded and emitted a `*.workers.dev` URL
    - `curl &lt;url&gt;/` returns 200 with body containing `Day 1 hello-world`
    - `curl &lt;url&gt;/ping` returns 200 with JSON body containing both `"ok":true` and `"row_count":1`
    - `wrangler d1 execute wbauth-day1-test --remote --command="SELECT * FROM hello"` returns at least 1 row
    - `.planning/phases/01-foundation-cryptographic-root/01-01-HOSTING-RESULT.md` exists, contains `STATUS: PASS`, includes the deployed URL, the database_id, and explicitly notes that D-01, D-02, D-03, D-04 are validated
    - If the test FAILED, the result file contains `STATUS: FAIL` with the exact error message and the entire phase is HALTED (no commit, escalate to user)
  </acceptance_criteria>
  <done>
    Worker is live on `*.workers.dev`, `/ping` returns row_count=1 from D1, the hosting result is documented in 01-01-HOSTING-RESULT.md as PASS, and Phase 1 is unblocked for Plans 02-04.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| developer machine → Cloudflare API | OAuth tokens stored locally by wrangler; D1 schema commands sent over HTTPS. |
| public internet → deployed Worker | Anyone can curl the `/` and `/ping` endpoints; this is intentional (it's a public hello-world). |
| Worker → D1 | In-Cloudflare-network binding (no internet exposure of D1). |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-01-01-01 | Spoofing | wrangler OAuth flow | mitigate | OAuth PKCE flow handled by wrangler 4.87.0; user verifies the consent dialog is on dash.cloudflare.com (not a phishing host). |
| T-01-01-02 | Information Disclosure | `database_id` committed to wrangler.jsonc in git | accept | Per Cloudflare docs the database_id is not a secret — it's a routing identifier; the actual data is access-controlled by the Worker and D1 binding. (This file gets reviewed in Phase 3 when real data is added.) |
| T-01-01-03 | Denial of Service | hello-world Worker getting 100k+ req/day | accept | Workers Free plan caps at 100k req/day. Hello-world Worker has no public listing; risk is negligible during Phase 1. |
| T-01-01-04 | Information Disclosure | seeded `Day 1 works` row leaking some secret | accept | The literal string `Day 1 works` contains no secret material; the `hello` table is a smoke-test fixture that Phase 3 drops. |
| T-01-01-05 | Tampering | malicious actor modifies wrangler.jsonc to redirect deploys to their account | mitigate | wrangler.jsonc is committed to git; any change is visible in PR review. The OAuth flow re-authenticates per session; no shared service tokens. |
| T-01-01-06 | Repudiation | user later claims they didn't approve Cloudflare account creation | accept | Account creation is intentional and recorded in 01-01-HOSTING-RESULT.md with the email used. |
</threat_model>

<verification>
1. `directory/wrangler.jsonc` has a real database_id (no `<paste-from-d1-create-output>` placeholder).
2. `directory/src/index.ts` reads from `env.DB` (proves D1 binding is used).
3. The deployed `*.workers.dev` URL responds to `/ping` with `{"ok":true,"row_count":1}`.
4. `wrangler d1 execute wbauth-day1-test --remote --command="SELECT * FROM hello"` returns ≥1 row.
5. `01-01-HOSTING-RESULT.md` exists and records `STATUS: PASS` with the deployed URL and database_id.
</verification>

<success_criteria>
- DIR-06 satisfied: hosting confirmed working with the developer's account on Cloudflare Workers + D1 free tier.
- Worker deployed at a `*.workers.dev` URL, accessible publicly, reading from D1.
- 01-01-HOSTING-RESULT.md documents the validated locked decisions (D-01, D-02, D-03, D-04).
- The whole rest of Phase 1 (Plans 02, 03, 04) is unblocked.
- If ANY step fails, the plan halts with `STATUS: FAIL` recorded; user is escalated; no Phase 1 work proceeds until D-04 escalation is resolved.
</success_criteria>

<output>
After completion, create `.planning/phases/01-foundation-cryptographic-root/01-01-SUMMARY.md` summarizing:
- The deployed `*.workers.dev` URL
- The D1 database_id
- Confirmation that D-01..D-04 are validated
- Reminder to downstream plans: `directory/src/index.ts` is throwaway; Phase 3 replaces it with the real JWKS backend
</output>
