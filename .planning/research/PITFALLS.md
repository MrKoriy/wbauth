# Pitfalls Research

**Domain:** Agent Identity & Pre-flight Policy Toolkit (Web Bot Auth + robots/ai/llms/MCP discovery + hosted directory)
**Researched:** 2026-05-03
**Confidence:** HIGH on Web Bot Auth / RFC 9421 specifics (Cloudflare and IETF docs are explicit and current); HIGH on Russia/OFAC and managed-host specifics (well-documented by primary sources); MEDIUM on OSS-distribution failure-mode causality (correlational evidence, not causal); MEDIUM on directory-abuse vectors (mostly inferred from analogous services).

> **Note on prompt-injection:** While reading the supplied context files, an attempt to inject MCP-server "instructions" was detected at the end of `strategic_memo_ru.md`. It has been ignored. This document follows the original task brief only.

---

## Critical Pitfalls

### Pitfall 1: Signature-Agent header missing, malformed, or not in `Signature-Input` component list

**What goes wrong:**
Cloudflare's verifier (and likely any future strict verifier) rejects the request with no useful error. The SDK appears to "work" — the request goes out signed — but the receiving WAF treats it as anonymous and challenges/blocks it. Looks like a bug in the WAF; is in fact an SDK bug.

**Why it happens:**
Three independent traps in the same header:
1. `Signature-Agent` is a Structured Field (RFC 8941) — its value MUST be a String, i.e. enclosed in **double quotes**: `Signature-Agent: "https://example.com/.well-known/http-message-signatures-directory"`. Naive string concatenation produces an unquoted URI that parses but fails verification.
2. The URI MUST be `https://`. `http://` URIs are rejected.
3. The header name `signature-agent` MUST appear in the component list inside `Signature-Input`. If the header is sent but not signed, Cloudflare rejects.

**How to avoid:**
- Build a single `set_signature_agent(directory_url: str)` helper that does all three: validates `https://`, wraps in `"…"`, and forces `signature-agent` into the component list.
- Use a structured-field library (Python: `http_sf` or `http_message_signatures` defaults) rather than string concatenation.
- Test against Cloudflare's public reference verifier (`cloudflareresearch/web-bot-auth`) and the Stytch example as part of CI.

**Warning signs:**
- "Verification works locally with our own verifier but fails on Cloudflare-protected sites."
- A passing unit test on signature creation but no integration test against Cloudflare reference verifier.
- README showing `Signature-Agent: https://...` (no quotes) as an example.

**Phase to address:**
Phase 1 (Python SDK Web Bot Auth core). Must include integration tests against `cloudflareresearch/web-bot-auth` reference verifier and the canonical IETF test vectors before any other feature ships.

**Citation:** Cloudflare bot docs, "Web Bot Auth" reference page; community thread "Web Bot Auth Signature Validation Failure".

---

### Pitfall 2: Wrong derived components signed (signing what Cloudflare doesn't accept)

**What goes wrong:**
SDK signs a "complete" RFC 9421 component list including `@query-param` or `@status`, or signs `@authority` and `@scheme` derived from a request that came through a TLS-terminating proxy (`@scheme=http`, `@authority` = internal hostname). Verifier rejects.

**Why it happens:**
- Cloudflare's verifier does not implement every RFC 9421 derived component. `@query-param` and `@status` are explicitly rejected. Cloudflare docs recommend `@query` (whole query string) instead.
- Behind nginx/Envoy/ALB, `req.TLS == nil` even on HTTPS traffic, so libraries default `@scheme=http`. Signature base does not match what the verifier reconstructs.
- `@target-uri` reconstructed differently across reverse proxies.

**How to avoid:**
- Ship a **"Cloudflare-safe profile"** that pre-selects the minimal components: `@method`, `@authority`, `@target-uri`, `content-digest`, `signature-agent`. Make this the default.
- Provide an `inspect_signature_base(request)` debug function that prints the exact bytes that will be signed — the #1 debugging affordance.
- Document explicitly: "Do NOT add `@query-param` or `@status`. If you must sign individual params, your signatures won't verify on Cloudflare."

**Warning signs:**
- Anyone proposing "let's support all RFC 9421 components." (Goal is interop with verifiers in the wild, not spec completeness.)
- Tests that use `localhost` exclusively — proxy-related issues are invisible there.

**Phase to address:**
Phase 1 (Python SDK). Cloudflare-safe profile is the default; "advanced" profile is a documented opt-in with a warning.

**Citation:** Cloudflare bot docs, "Web Bot Auth" reference page (explicit unsupported components list); RFC 9421 §2.5.

---

### Pitfall 3: Clock skew + too-short `expires` window = silent intermittent failures

**What goes wrong:**
Signatures verify in dev (machine in sync with NTP), then fail in prod intermittently. Worst case: works for the first user, fails for the next, with no log entry that explains why.

**Why it happens:**
- `created` and `expires` parameters are signed; verifier rejects if current time is past `expires` or `created` is "too far" from server time.
- Network latency + intermediate proxy buffering can eat 1-3 seconds between signing and Cloudflare seeing the request.
- Common SDK default: `expires = created + 30` seconds. Real default needs to be 60-300 seconds.
- Clock-skew tolerance differs per verifier (Kerberos default = 5 min; many implementations default to 60-120s); not specified by RFC 9421.

**How to avoid:**
- Default `expires = created + 60` seconds. Allow override.
- Document: "If your machine is more than 5 seconds out of NTP sync, signing will work but verification will fail intermittently."
- Provide a `diagnose()` function in the SDK that fetches a known signed-bot endpoint and reports back-and-forth latency + clock-skew estimate.
- In `agentpassport.dev` directory backend: serve current server time in a `/time` endpoint so SDK clients can self-correct.

**Warning signs:**
- Bug reports that say "works some of the time."
- Default expires < 30s in any code path.
- SDK has no NTP/clock-check facility.

**Phase to address:**
Phase 1. The `/time` endpoint and `diagnose()` ship with the first directory backend release.

**Citation:** RFC 9421 §3.2.1 (Created/Expires); AWS SDK clock-skew correction blog (canonical 5-minute window); JWT clock-skew literature.

---

### Pitfall 4: Private Ed25519 key accidentally logged or committed

**What goes wrong:**
`__repr__` of the key object prints raw bytes; `print(config)` dumps everything; debug logging at INFO level captures the request including the keypair object. Key ends up in CloudWatch / Sentry / GitHub.

**Why it happens:**
- Default `__repr__` of Python bytes objects shows hex/escape; many libraries don't override `__repr__` for key classes.
- Developers `pickle.dumps(client)` to debug, accidentally serialize the key.
- Test fixtures with real keys committed to repos (especially when "test against Cloudflare's directory" requires a real published key).
- File-permission default of `0o644` on key files written by SDK; `umask` doesn't always rescue this.

**How to avoid:**
- Wrap private key in a class whose `__repr__` and `__str__` return `"<Ed25519PrivateKey REDACTED>"`. Override `__reduce__` to refuse pickling.
- SDK never logs full request objects. Provide a `redacted_dict(request)` helper.
- When SDK writes a key file, explicitly `os.chmod(path, 0o600)` and verify by reading back stat.
- Refuse to load a key file with permissions broader than `0o600` on POSIX. Print a clear remediation error.
- Ship a `pre-commit` hook config (`detect-private-key` from pre-commit-hooks) in the README's "production checklist."
- Provide official test vectors with **publicly known** keys (the IETF test-vector set) so users never need real keys for testing.

**Warning signs:**
- Any `logger.debug(f"signing with {key=}")` in code review.
- Any test fixture file ending in `.pem` checked into the repo.
- SDK creates key files without chmod.

**Phase to address:**
Phase 1 (Python SDK). The redacted-repr wrapper and the file-permission check are non-negotiable in the first release. They cannot be retrofitted after a key leak.

**Citation:** SSH ecosystem precedent (UNPROTECTED PRIVATE KEY FILE warnings); general SDK security hygiene. No public Web Bot Auth-specific leak yet, but there will be one — make sure it isn't from this SDK.

---

### Pitfall 5: Key-file storage path conflicts with other tools

**What goes wrong:**
SDK defaults to `~/.config/agentpassport/key.pem` or `~/.ssh/agent_id_ed25519`. User has another tool that touches the same path; key gets overwritten or corrupted. Or: SDK writes to `/tmp/agent_key.pem` "for testing," user forgets, key leaks via `/tmp` cleanup.

**Why it happens:**
- No XDG-compliant default path discipline.
- "Convenience" defaults that store unencrypted keys in well-known locations.
- TOFU (trust-on-first-use) flow that auto-generates a key on first run with no prompt.

**How to avoid:**
- Default path: `${XDG_DATA_HOME:-~/.local/share}/agentpassport/<key-id>.pem`. Never `/tmp`. Never `~/.ssh/`.
- Auto-generation requires either explicit `generate_key=True` arg or interactive confirmation. Print the path, the keyid, and the command to publish to a directory.
- Document that production deployments should use environment variable `AGENTPASSPORT_KEY` (PEM body, base64) or a secret-manager fetcher (`AGENTPASSPORT_KEY_FETCHER=aws-secrets:agent-key`) — not files.
- Refuse to overwrite an existing key file without `force=True`.

**Warning signs:**
- Any default path in `/tmp`, `~`, or `~/.ssh`.
- Auto-generate-on-import behavior.
- No path-conflict check.

**Phase to address:**
Phase 1. Default-path policy locks early because changing it later breaks every existing user.

---

### Pitfall 6: TOFU fingerprinting confused with directory-published verification

**What goes wrong:**
Verifier tooling (or downstream library users) treats the first key seen as canonical and caches it. Attacker rotates key via the directory; verifier still trusts old key. Or: attacker publishes a key and verifier accepts it without checking the operator binding.

**Why it happens:**
- Web Bot Auth has TWO discovery models that look similar:
  - Local `keyid` cache (TOFU-ish — works if the verifier already knows you).
  - `Signature-Agent` directory lookup (operator-published, requires HTTPS fetch).
- Implementers conflate them, or skip the directory lookup "for performance" and pin keys.
- Directory format is still draft (`draft-meunier-http-message-signatures-directory`); spec evolution can break old caches.

**How to avoid:**
- Verification SDK MUST fetch the directory on key rotation; provide a configurable cache TTL (default: 24h, max: 7 days).
- Distinguish in API: `verify_with_directory(request)` vs. `verify_with_pinned_key(request, key)`. No mixing.
- Document the threat model explicitly: "Web Bot Auth identifies the bot operator. It does NOT prove the bot is well-behaved or authorized for this site."
- For directory backend (`agentpassport.dev`): serve immutable URLs per key (`/keys/<thumbprint>`) so verifiers can cache forever; current keys at `/.well-known/...`.

**Warning signs:**
- Verifier code that accepts `keyid` without resolving against any directory.
- Cache TTL = "until process restart."
- README that says "easy: just pin the public key once."

**Phase to address:**
Phase 1 for SDK key resolution; Phase 2 for directory backend cache-control headers and immutable URL design.

**Citation:** `draft-meunier-http-message-signatures-directory-04`; RFC 9421 §7.2.6 "Multiple Signature Confusion."

---

### Pitfall 7: "It works, looks done" but Cloudflare directory submission never approved

**What goes wrong:**
SDK signs, verifier code passes, demo works against test endpoints. Three months later, no agents using it have been added to Cloudflare's verified-bot list. Project's value collapses because Cloudflare-protected sites still block the agent.

**Why it happens:**
- Cloudflare's submission flow requires a manual review via the Cloudflare dashboard (Bot Submission Form). Approval can take weeks/months and may need explicit operator outreach.
- Documentation gates: requires a published `/.well-known/http-message-signatures-directory`, a stable HTTPS host, a clear operator policy page.
- "A bot cannot be registered as both a verified bot and a signed agent" — picking the wrong category is rejection.
- The project itself isn't a bot; it's a TOOLKIT for bots. The directory submission has to be done by each user, not by the project author.

**How to avoid:**
- Ship a `quickstart` that walks through the Cloudflare submission process explicitly: which form, which category (signed agents), what Validation Instructions URL to provide, common rejection reasons.
- Provide a `python -m agentpassport check-submission-readiness <directory_url>` command that simulates Cloudflare's checks: HTTPS reachable, JWKS valid, `Signature-Agent` works end-to-end.
- Coordinate with `agentpassport.dev` directory: any agent published there gets a pre-baked `Signature-Agent` URL that already meets Cloudflare's hosting requirements. Eliminates the "where do I host my JWKS" friction.
- Keep ONE working live demo agent (e.g., `agent.agentpassport.dev`) that is itself approved on Cloudflare's signed-agent list, so users can compare.

**Warning signs:**
- README says "submit to Cloudflare" without a step-by-step.
- No on-call / no email forwarding from `agentpassport.dev` to handle the inevitable "Cloudflare rejected my submission" issue during army leave.

**Phase to address:**
Phase 2 (directory + Cloudflare integration documentation). Critical: do this BEFORE army leave so a working precedent exists.

**Citation:** Cloudflare bot docs, "Verified bots" and "Signed agents" pages.

---

### Pitfall 8: robots.txt parser ambiguity → SDK reports wrong policy

**What goes wrong:**
`inspect(url)` returns "you are allowed" but the site actually blocks the agent. User loses trust in pre-flight policy entirely.

**Why it happens:**
- robots.txt grammar is case-sensitive in undocumented ways (`User-agent: GPTBot` matches `GPTBot` exactly; `gptbot` does not).
- Multiple bots, longest-match-wins rules, `Allow:` overrides on `Disallow:` paths — every Python `urllib.robotparser` has known edge-case bugs.
- Many sites publish HTML 200 pages at `/robots.txt` (SPA catch-alls, soft-404s). SDK parses HTML as text → returns "no rules" → claims "everything allowed" — exactly wrong.
- AI-bot-specific user agents proliferate: GPTBot, ChatGPT-User, OAI-SearchBot, ClaudeBot, anthropic-ai, PerplexityBot, Google-Extended, Applebot-Extended, Meta-ExternalAgent, Amazonbot, Bytespider, plus dozens more added quarterly. Hard-coding lists rots fast.

**How to avoid:**
- Use Google's `robotstxt` reference parser (port to Python via `protego` or `reppy` — both wrap the canonical Google parser logic). Do NOT use `urllib.robotparser`.
- Validate `robots.txt` content-type and structure before parsing. If response is HTML, return an explicit `RobotsParseError("site returned HTML for robots.txt — assume disallowed")` rather than `allowed=True`.
- For each known AI bot, encode the policy AND the operator (`{"GPTBot": "openai", "ClaudeBot": "anthropic"}`). Source list from `ai-robots-txt/ai.robots.txt` (community-maintained), refresh quarterly via CI.
- Return a structured result: `{rule_matched: "Disallow: /api/", user_agent_matched: "ChatGPT-User", confidence: "exact"|"wildcard"|"none", source_url: "https://example.com/robots.txt", fetched_at: ts}`. Never just `bool`.

**Warning signs:**
- `inspect()` returns `True/False` boolean rather than a rich object.
- Dependency on `urllib.robotparser`.
- No test against a site that returns HTML for robots.txt (e.g., a SPA catch-all).

**Phase to address:**
Phase 3 (pre-flight inspector). Test corpus must include: `httpbin.org`, `example.com`, a SPA-catch-all site, a site with no robots.txt at all, and a site that returns 403 on robots.txt.

**Citation:** Paul Calvano's "AI Bots and Robots.txt" study (2025); Google's robotstxt parser.

---

### Pitfall 9: llms.txt overpromise — selling something that doesn't move the needle

**What goes wrong:**
SDK markets "respects llms.txt" as a value prop. Users adopt expecting AI-related compliance benefit. Reality: zero major AI crawler measurably acts on llms.txt; SE Ranking 300k-domain study and ALLMO 94k-URL study both show no citation uplift. Users feel misled.

**Why it happens:**
- llms.txt is culturally meaningful (844k sites adopted) but technically a markdown file with no enforcement and no major LLM operator officially honoring it as access control.
- Conflates two purposes: AI-citation hint vs. crawl/access control. robots.txt is the latter; llms.txt is the former, weakly.
- Easy to confuse with `ai.txt` (Spawning, content-licensing focused, also weakly adopted) — they are NOT the same standard.

**How to avoid:**
- Pre-flight inspector returns llms.txt content, but **labels it correctly**: `{type: "soft_hint", enforcement: "voluntary", spec_status: "informal", honored_by: ["mintlify", "cursor", "anthropic_partial"], not_honored_by: ["google_search", "openai_crawler"]}`.
- README explicitly says: "We surface llms.txt because some agents may use it for context. We do NOT claim it provides any access control. For real bot policy, use robots.txt + Web Bot Auth."
- Do NOT use llms.txt presence to infer ai.txt or vice versa.

**Warning signs:**
- Marketing copy that says "respects llms.txt" without qualification.
- API that returns "you may scrape this site" based on absence of llms.txt.

**Phase to address:**
Phase 3. Spec-status labels and tone are decided in the inspector design phase.

**Citation:** AEO Engine "llms.txt Zero Usage" (2026); SE Ranking 300k-domain study; ALLMO citation uplift study.

---

### Pitfall 10: Python/TypeScript SDK API drift

**What goes wrong:**
Python SDK is the author's daily driver and gets fixes immediately. TypeScript SDK (delegated to coding agents per project plan) silently lags by 3-6 weeks. During army leave, drift expands; TS users hit edge cases Python users don't. Bug reports get filed against the Python repo for TS-only behavior.

**Why it happens:**
- Two SDKs in two languages by one solo dev with no CI parity check = guaranteed drift.
- Web Bot Auth profile evolves (Cloudflare adds/removes accepted components); manual sync required.
- Test vectors live in one repo; the other gets a copy that goes stale.

**How to avoid:**
- **Single source of truth for test vectors**: a JSON file of canonical request/signature pairs, published in a separate `agentpassport-vectors` repo. Both SDKs consume it via CI. Drift is mechanically detectable.
- **Profiles encoded as JSON**: `cloudflare-safe-profile.json` lists the components, header requirements, expires defaults. Both SDKs load this at runtime. Adding a profile = editing JSON, not two SDKs.
- Publish a **conformance test runner** (Docker image) that any SDK can be run against. Make it a release gate.
- During army leave, set up a GitHub Action that auto-files an issue if the conformance runner detects drift.

**Warning signs:**
- Test vectors live as separate Python/TS literals.
- "Profile" exists only in code, not as data.
- One SDK's release notes don't mirror the other's.

**Phase to address:**
Phase 1 (Python SDK) ships with the test-vectors repo and conformance runner. Phase 2 (TS SDK) reuses both — never duplicates.

---

### Pitfall 11: Dependency rot during 6-month army leave

**What goes wrong:**
Project returns from 6 months silent. `pip install agentpassport` fails because:
- `cryptography` had a CVE; old version yanked.
- `httpx` had a major version bump; downstream signature middleware broken.
- `pydantic` v2 → v3 transition; field validators broken.
- Python 3.12 EOL; CI matrix doesn't test 3.13/3.14.
- `requests` 3.0 finally shipped, breaking the `requests` integration.

**Why it happens:**
- Pinned deps go stale; floating deps break.
- 6 months in agent ecosystem = 1-2 MCP spec versions, possibly a Web Bot Auth WG charter change.
- CI runs against latest at HEAD by default; nothing catches "old version still works for users locked to it."

**How to avoid:**
- **Pin upper bounds aggressively**: `cryptography>=42,<46`, `httpx>=0.27,<0.30`. Better to break early than silently.
- Use **uv lockfile** committed to the repo for reproducible installs; document `uv sync` as the recommended install path.
- Set up **Dependabot/Renovate** to file PRs but configure auto-merge ONLY for security patches in tested-CI branches. No human review for green security PRs.
- Set up a **monthly scheduled CI run** even with no commits — catches "still installs cleanly" regressions.
- **Bus-factor README section**: at top of README, state "Solo maintainer on military service until Q4 2026; for urgent issues contact [email]." Reduces the 36k+ "is this abandoned" issue noise.
- Pre-flight register a freeze branch (`v1.x-frozen`) that users can pin to: `pip install agentpassport>=1.0,<2`. Promise compatibility on this line for 12 months.
- Before army leave: open a **"known good" GitHub issue** that pins the install command tested 24h before leaving.

**Warning signs:**
- Floating dep ranges (`cryptography>=42`).
- No lockfile in the repo.
- No scheduled CI.
- No `<2` upper bound in any dep.

**Phase to address:**
Phase 5 (pre-leave hardening). Dedicated phase: "freeze the floor, document the bus factor, schedule the canary."

**Citation:** HeroDevs "OSS tech stack 18 months" guide; Socket.dev solo-maintainer report (60% considering quitting, 60% solo); Node.js maintenance issue #113.

---

### Pitfall 12: Cloudflare/AWS verifier behavior changes mid-army-leave

**What goes wrong:**
Cloudflare ships a stricter verifier enforcement — e.g., starts requiring `signature-agent` to be present (it does as of 2025) — and existing users of the SDK silently start failing. SDK is "frozen" but the world isn't.

**Why it happens:**
- Web Bot Auth IETF draft is ACTIVE; profile evolves.
- Cloudflare/AWS unilaterally tighten requirements without IETF coordination.
- Project author is unreachable for 6 months.

**How to avoid:**
- **Defensive defaults**: SDK includes EVERY component Cloudflare currently requires plus likely-future ones (e.g., `signature-agent` is already in the default profile, even before it was strictly required).
- **Conformance canary**: a GitHub Action runs daily against `cloudflare-bot-test.example.com` (Cloudflare's reference) and posts to a Slack/Discord webhook + opens an issue if conformance breaks. Set this up before leaving.
- **Monitor IETF mailing list** via a public archive RSS → email; configure email forwarding to a friend who can post a Github issue if a draft revision drops.
- Document the **escape hatch**: even if the SDK is broken, a user can manually craft a signed request using `pip install http-message-signatures` (the underlying lib). Make the SDK a thin wrapper, not a re-implementation.

**Warning signs:**
- SDK reimplements RFC 9421 from scratch.
- No daily canary.
- "Defensive" components excluded for "spec purity."

**Phase to address:**
Phase 5 (pre-leave hardening) — set up the canary and the IETF watcher.

---

### Pitfall 13: Russian payment lockout if monetization sneaks in

**What goes wrong:**
Project author (RU-resident) accidentally accepts payment via PayPal/Stripe/even Lemon Squeezy and is permanently banned from receiving funds, because OFAC IT-services determination (effective 12 Sep 2024) prohibits US persons from providing IT support services to persons located in Russia. Even Lemon Squeezy and Paddle have grey-area exposure.

**Why it happens:**
- Free OSS plus a "tip jar" (e.g., GitHub Sponsors, Open Collective) is enough to trigger US-payment-rail KYC flagging if author lists Russian residence.
- Hosted directory `agentpassport.dev` has a tempting "premium tier" addition under contributor pressure.
- Domain registrars and infra providers may pull service if a connected account flags as RU.

**How to avoid:**
- v1 is **strict OSS, no payment surface anywhere**. No GitHub Sponsors, no Buy Me a Coffee, no donation links, no "premium" tier — even a free one. Any monetization is post-army-leave AND post-relocation.
- `agentpassport.dev` directory submission flow: free, no account, no KYC, no email collection (or only optional opt-in for security advisories).
- Hosting on Railway or Fly.io (both reportedly accept RU cards as of 2026 per project memo; verify in week 1). Pay annually if possible to reduce monthly billing fragility.
- Domain registrar: Namecheap historically accepts RU cards; Cloudflare Registrar refuses many RU billing addresses. Verify before registering critical domain.
- Keep a **personal fallback card** (e.g., Wise debit card via a relative outside RU, or Armenian card from past travel) for paying for the domain renewal during army leave. Auto-renew enabled. Multi-year registration if possible.
- Document in private notes: which infra accepts which card. Create a recovery doc for whoever has access during leave.

**Warning signs:**
- A donation link added "just temporarily."
- Domain set to expire within 18 months without auto-renewal.
- A single point of payment failure for `agentpassport.dev` infrastructure.

**Phase to address:**
Phase 0 (project setup) — this is a foundational policy decision. Phase 5 (pre-leave hardening) — verify all renewals are funded for >18 months.

**Citation:** OFAC "Prohibition on Certain Information Technology and Software Services" determination (effective 2024-09-12); GVA Capital $216M penalty (July 2025); strategic memo `strategic_memo_ru.md`.

---

### Pitfall 14: PyPI / npm publishing identity flagged

**What goes wrong:**
PyPI / npm don't currently sanction Russian developers en masse (Russia is not on the GitHub-blocked-country list per arxiv 2404.05489). But:
- Publishing under a `.ru` email or with Russia in profile metadata gives reviewers a bias-flag.
- A future enforcement action could block account-level publishing.
- 2FA on PyPI is mandatory; if 2FA device is lost during army leave, account is locked indefinitely.

**Why it happens:**
- Bus factor: account access tied to one human + one phone.
- US-export-control enforcement uncertainty; future tightening possible.

**How to avoid:**
- **2FA backup codes printed on paper**, stored with a trusted person + a second copy in a separate location. Not in any cloud.
- Publish under a **project-scoped account** (`agentpassport-bot@protonmail.com`, not the personal email) so the account is transferable / shareable in emergency.
- Use **PyPI trusted publishers** (OIDC from GitHub Actions): no manual 2FA needed for releases; the publish authority lives in the GitHub repo's workflow, which is scoped per environment.
- For npm: same — use `npm publish` with provenance from GitHub Actions, not a local laptop.
- Pre-leave: cut a **release tag** that publishes a stable v1.x. Make it the recommended install. Drift won't break anyone for the locked version.

**Warning signs:**
- 2FA on a single phone with no backup codes.
- Publishing from a laptop, not from CI.
- Personal email tied to package ownership.

**Phase to address:**
Phase 5 (pre-leave hardening). Trusted publisher setup MUST happen before leave.

**Citation:** GitHub Trade Controls policy; arxiv 2404.05489 "Sanctions on GitHub Developers"; PyPI trusted publishers docs.

---

### Pitfall 15: Hosted directory cost overruns / DoS

**What goes wrong:**
`agentpassport.dev` is free and public. Someone runs a script that registers 100k fake bots. Or someone's misconfigured agent hammers the directory at 10 RPS for weeks. Author is on army leave; bills go to a card with limited funds; service is suspended; entire identity infrastructure collapses for legitimate users.

**Why it happens:**
- Free public services with no per-IP / per-account quotas always get abused.
- Postgres write-heavy operations (registration) are expensive on managed hosts.
- Egress charges on JWKS lookups (signature verifiers fetch the directory) can spike if an agent accidentally fetches per-request instead of per-key-rotation.

**How to avoid:**
- **Per-IP rate limit** on registration: 10/day per IP, hard. Use slowapi + Redis (Upstash free tier) or fastapi-limiter.
- **Per-key rate limit** on lookup: HTTP cache headers `Cache-Control: public, max-age=86400, immutable` on `/keys/<thumbprint>` (immutable URLs); Cloudflare CDN in front of the directory. Aggressively use Cloudflare's free tier — caching reduces origin load 100x+.
- **Hard spending caps**: Railway/Fly both expose monthly spend caps. Set to $20/month. If hit, service goes read-only (still serves keys; no new registrations) rather than down.
- **Registration moderation queue** (post-army-v2): registrations don't go live for 24h; trivially-fake names rejected.
- **No email captured at registration**, so spam-registration creates no spam-list; reduces incentive.
- **Postgres backup automation**: managed providers (Supabase, Neon) auto-backup; verify retention period is >30 days. For "frozen" mode: nightly export to a dumb S3-compatible bucket via cron, off-platform redundancy.

**Warning signs:**
- No rate limit at all.
- No spending cap configured.
- No CDN in front of the directory.
- Registration with email field that someone could harvest.

**Phase to address:**
Phase 4 (directory backend). Rate limits ship with v1; spend caps configured before public launch.

**Citation:** Cube Exchange/Packetlabs replay-attack guides (general); Wallarm API abuse prevention; OOPSpam.

---

### Pitfall 16: Directory abuse — someone claims to be Google's agent

**What goes wrong:**
Someone registers `agent-name: "GoogleBot"`, `operator: "Google LLC"` on `agentpassport.dev`. Their signed requests carry that identity. Sites that look up the directory believe a malicious actor IS Google.

**Why it happens:**
- Free public directories with no operator-verification have no defense against this.
- Web Bot Auth signature proves "this key signed this request" — it does NOT prove the key belongs to the claimed operator.
- Common conflation: "verified bot directory" (Cloudflare's, which DOES verify operator identity through manual review + IP/ASN matching) vs. "self-published key directory" (just a key store).

**How to avoid:**
- **Be explicit about scope**: `agentpassport.dev` is a SELF-PUBLISHED key directory. Every page/API response says: "Identity claims are unverified. Use this for key lookup, not operator authentication."
- **Reserve the obvious operator names** at launch: `google`, `googlebot`, `openai`, `chatgpt`, `anthropic`, `claudebot`, `microsoft`, `bingbot`, `cloudflare`, `meta`, `apple`, `amazon`. Disallow registration with these strings or require email verification at the corresponding domain.
- **Display provenance prominently**: show "Registered: 2026-05-12 from IP 1.2.3.4. Email verified: no. Domain ownership verified: no." on every directory entry.
- **Optional: domain-ownership challenge** (later v2): operator publishes `/.well-known/agentpassport-claim/<token>` to prove domain control before claiming `operator: "openai.com"`.
- Document that **for production trust**, sites should rely on Cloudflare's verified-bot directory + IP allowlists, not on `agentpassport.dev`.

**Warning signs:**
- Registration form lets you set arbitrary `operator` field with no verification.
- No reserved-name list.
- Marketing claims `agentpassport.dev` provides "identity verification" rather than "key publication."

**Phase to address:**
Phase 4 (directory). Reserved-name list + provenance display in v1; domain-ownership challenge in v2.

---

### Pitfall 17: Documentation becomes the bottleneck for non-native English author

**What goes wrong:**
Project ships great code, but README is opaque or stilted. First wave of HN/Twitter users skim and bounce. GitHub stars cap at ~300 instead of growing past 1k. Browser Use / Stagehand maintainers don't link in their docs because the project doesn't read as polished.

**Why it happens:**
- Written-by-Russian-author-in-English fingerprint is real and detectable: missing articles, comma-spliced sentences, German-style noun-stacking, calques like "make download" instead of "download."
- LLMs translate/polish well at sentence level but introduce inconsistencies at document level: terminology drift across sections, hallucinated facts, broken markdown structure.
- "Translated" docs read as marketing copy, not as operational documentation — wrong register for OSS audience.

**How to avoid:**
- **One human native-English review pass per release**, paid or favor-traded. Cost: $50-200 on Upwork or Fiverr or via the Russian-tech diaspora in the US/UK. Worth it.
- **Structural template** for every page: H1 → 1-paragraph value statement → 30-second code example → links to deeper pages. No prose-heavy intros.
- **Code-first documentation**: every concept introduced via 5-line code block first, prose explanation second. Code is language-neutral.
- Use LLM polish for **sentence-level cleanup only** — never let it rewrite section structure, never let it generate "explanations" of code.
- **Glossary file** in the repo with canonical translations of all key terms (`Подпись → signature`, `Каталог → directory`). Reference it in every doc-related PR review.
- README **30-second test**: open in incognito, time how long until you understand "what is this and how do I install it." If >30s, restructure.
- Video demo (Loom) is recorded by the author with a SCRIPT pre-edited by a native speaker. Don't improvise voice-over.

**Warning signs:**
- README opens with "In nowadays AI agents..." or "We are excited to introduce..."
- Section headers are full sentences instead of noun phrases.
- Same concept named two different things on two pages.
- Loom video has 30+ filler words ("uh", "so").

**Phase to address:**
Every phase. Add to definition-of-done: "docs reviewed by native-English speaker before tag."

**Citation:** arxiv 2508.02497 "Bridging Language Gaps in OSS with LLM-Driven Documentation Translation."

---

### Pitfall 18: README that doesn't show value in 30 seconds

**What goes wrong:**
README opens with origin story / problem motivation. By the time the reader sees the import statement, they've left. Star velocity caps below the ~1k/14-day threshold the strategic memo identifies as the kill signal.

**Why it happens:**
- Common author instinct: justify why the project exists before showing what it does.
- Embedded GIFs/demos are big files — author skips to "ship later," they never get added.
- Quickstart code requires multiple imports / a config file / a hosted account before showing a result.

**How to avoid:**
- README structure (locked):
  ```
  # Project Name
  One-sentence value: "Sign your agent's HTTP requests so Cloudflare/AWS stop blocking it as anonymous."
  [10-15s GIF: import, decorate, request goes through]
  ## Install: pip install agentpassport
  ## Use:
      from agentpassport import signed
      @signed()
      def fetch(): return httpx.get("https://example.com")
  [Three real users' logos / quotes]
  Why this exists | Docs | Discord
  ```
- **GIF is mandatory before public launch**. Record it on day 1; it can be ugly v1, polish v2.
- **Quickstart must work in ZERO config**. Auto-generate a key on first call, print "your key is at ~/.local/share/agentpassport/...". Use a public dev directory if needed.
- **Three real-user quotes** — even pre-launch, recruit 3 Browser Use / Stagehand users for one-line testimonials in week 1.

**Warning signs:**
- README's first paragraph doesn't include code.
- No GIF/video at the top.
- Quickstart requires registering for a service.

**Phase to address:**
Phase 5 (launch prep). README locked 48h before public launch with this template.

**Citation:** "Projects with demo GIFs get 40% more GitHub stars on average"; strategic memo's 1k stars / 14 days kill-signal.

---

### Pitfall 19: Issue / PR backlog perception during army leave

**What goes wrong:**
Six months of unanswered issues = de facto "abandoned" signal. New users see 47 open issues with no maintainer response, one stale PR, last commit 5 months ago. They don't adopt. On return, salvaging the project takes 2x more effort than maintaining it would have.

**Why it happens:**
- 36k+ "is this project abandoned" issues exist on GitHub. Pattern is well-known.
- No automated triage; no community moderators; no clear maintainer-status signaling.

**How to avoid:**
- **Pinned issue at top of repo**: "Maintainer status: solo dev on military service until ~Nov 2026. Issues will be triaged in batches. For urgent security issues, email security@agentpassport.dev (forwarded to a designated friend)."
- **GitHub Action auto-labels new issues**: `triage-on-return`, `community-help-welcome`, `security-urgent`.
- **Auto-comment on new issues**: friendly note, expected response time, link to community Discord.
- **Designate 1-2 community moderators** before leaving (recruit from early users): give them triage labels permission. Not commit access.
- **Auto-close stale issues** (90 days no activity, with bot warning at 60). Reduces backlog perception.
- **Status badge in README**: `Maintainer: AFK until 2026-11 [why]` linking to the pinned issue.

**Warning signs:**
- No pinned status issue.
- No auto-labeling.
- No designated moderator.
- README says nothing about leave.

**Phase to address:**
Phase 5 (pre-leave hardening). Set up moderators + automation 2 weeks before leave.

---

### Pitfall 20: Cloudflare/AWS ship a built-in agent SDK and obsolete this project in 3 months

**What goes wrong:**
Cloudflare publishes `cloudflare/agent-sdk` as an official npm package; AWS publishes `aws-agent-passport-sdk` for AgentCore. They have the bot-list relationships; they have the trust. This project's relevance evaporates.

**Why it happens:**
- This is the most plausible competitive scenario per the strategic memo and per Cloudflare's "Cloud 2.0 — agentic cloud" announcements (April 2026).
- Cloudflare already owns `cloudflareresearch/web-bot-auth`. AgentCore Identity is generally available with OBO support (April 2026 release).

**How to avoid (design as additive, not competitive):**
- **Multi-platform from day 1**: support Cloudflare AND AWS AgentCore AND Akamai AND DataDome verifiers. The project's value is "one SDK, all verifiers" — not "best Cloudflare SDK."
- **Pre-flight policy is the moat**: Cloudflare is unlikely to ship `inspect(url) → robots.txt + ai.txt + llms.txt + MCP discovery` because they don't care about non-Cloudflare sites. This is the differentiator that survives even if Cloudflare ships their own signing SDK.
- **Hosted directory `agentpassport.dev` is platform-neutral**: a Cloudflare-issued key works there too. Position as "Switzerland of agent identity."
- **Integration packs over implementations**: own the integration with Browser Use, Stagehand, Playwright, OpenAI Agents SDK. Even if Cloudflare ships an SDK, our integration packs become the bridge.
- **Don't compete on "first to ship Web Bot Auth Python SDK"** — compete on "first to ship cross-verifier identity + policy SDK with the framework integrations agent devs actually use."

**Warning signs:**
- Project description that says "Web Bot Auth SDK for Python" — too narrow, easily superseded.
- No support for non-Cloudflare verifiers in roadmap.
- Directory `agentpassport.dev` defaults to Cloudflare-only key format.

**Phase to address:**
Phase 0 (positioning) and Phase 3 (inspector — the moat). The narrative work matters as much as the code.

**Citation:** AWS Bedrock AgentCore announcements (April 2026); Cloudflare "Agents Week 2026" review; project memo `Out of Scope` section.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Skip TypeScript SDK in v1, ship Python only | 50% less work to first release | Loses entire Browser Use / Stagehand audience (the highest-leverage user base); makes "OSS-first wedge" thesis weaker | Acceptable for week-1 alpha; not for v1.0 release |
| Hard-code Cloudflare-only profile | Faster ship, fewer edge cases | Easily-superseded by Cloudflare's own SDK; killed by pitfall 20 | Never — at minimum, keep AWS profile in the codebase even if not advertised |
| Use `urllib.robotparser` instead of protego/reppy | 0 dependencies, instant integration | Wrong parsing on edge cases → trust loss when SDK reports incorrectly | Never — protego is one dep, the trust cost is compounding |
| Skip `Signature-Agent` because the IETF draft is still moving | Simpler signing code | Cloudflare rejects every signed request; SDK appears broken | Never — Cloudflare requires it as of 2025 |
| Auto-generate key on first import, no prompt | "Just works" first run | Surprise key files, accidental commits, wrong permissions | Never — explicit `generate_key()` call only |
| Single Postgres on Supabase, no read replica | Cheap, simple | One PostgreSQL major-version upgrade event during army leave can break for hours-days | Acceptable for v1; document the failure mode in pre-leave checklist |
| No CDN in front of directory | One less dep, one less account | First viral moment = surprise $500 egress bill | Only for first 30 days post-launch with monitoring; add CDN before public push |
| Hard-coded user-agent allowlist for known AI bots | Quick `inspect()` accuracy | Stale every quarter; new bots like `Meta-ExternalAgent` ship monthly | Acceptable if list is sourced via CI from `ai-robots-txt/ai.robots.txt` and refreshed nightly |
| Documentation in author's English, no review | Fastest ship | Star velocity capped, perceived as low-quality | Only for internal/dev docs; user-facing docs need review |
| Signing the entire request body (`content-digest`) by default | Strongest security posture | Breaks for streaming uploads, multipart, and certain framework integrations | Default ON for GET; default OFF for POST with explicit opt-in |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| `requests` library | Passing the auth handler to `Session.auth =` and then forgetting that requests applies auth AFTER body serialization, breaking `content-digest` | Use a custom `HTTPAdapter` that hooks into `send()` after body is finalized, or wrap `Session.send` |
| `httpx` | Using `httpx.AsyncClient` with sync signing code blocks the event loop while computing Ed25519 sign (cheap but not free) | Run signing in a thread executor only when batched; for single requests, sync signing is fine |
| `aiohttp` | Middleware order matters: signing must run AFTER body is set but BEFORE the request is serialized to wire format | Use `aiohttp.ClientSession`'s `request_class` override; document the ordering explicitly |
| Playwright (TS) | Trying to sign Playwright's own browser-issued requests; Playwright uses Chrome's network stack which won't expose hooks at the right layer | Sign only requests made via `page.request` (Playwright's APIRequestContext); document that browser-context navigations CAN'T be signed via WBA |
| Browser Use | Bypassing the agent's HTTP layer because Browser Use calls Playwright internally | Provide an integration pack that wraps Browser Use's `LLMClient` HTTP layer specifically, not Browser Use itself |
| OpenAI Agents SDK | Default `OpenAI()` client doesn't expose request hooks | Use `openai.OpenAI(http_client=httpx.Client(...))` with our signed client; document this explicitly |
| Cloudflare Workers (TS) | Web Crypto API uses different key format than Node's `crypto` module | Test on `wrangler dev` AND Node; don't assume parity |
| Supabase (directory backend) | Auto-PG upgrades during army leave can break PostgREST schema bindings (May 30 2026 GRANT change is a known breaking change) | Pin to Supabase Postgres 15 explicitly; do the GRANT migration BEFORE leave |
| Railway / Fly.io | Card declines silently; only email notification | Auto-renew + alternate payment method on file + email forwarding from billing alerts |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Signing every request in a loop without caching keypair | CPU spikes; 5-10x slower than needed | Cache the loaded keypair object, not the bytes; load once per process | At ~100 req/s sustained |
| Fetching the directory on every verification | Network bound; per-request 200ms latency penalty | Cache directory response with `Cache-Control` headers respected (max-age + ETag); use `httpx`'s built-in caching | At ~10 req/s sustained verification |
| Not using `Cache-Control: immutable` on `/keys/<thumbprint>` | Verifiers re-fetch every minute; egress bills explode | Serve immutable URLs per key thumbprint; current-key endpoints are short TTL but redirect to immutable URL | At first viral moment (~1k+ verifiers) |
| Blocking event loop while parsing 1MB+ robots.txt | Async server hangs | Cap robots.txt fetch size to 500KB; parse in thread executor for files >50KB | At sites with crazy-large robots.txt (e.g., reddit.com) |
| Synchronous DNS lookup during signing | First-request latency spike | Pre-warm DNS for known directory hosts at startup | Only matters for cold-start serverless |
| In-memory rate-limit on directory backend | Reset on every deploy / restart; lost protection | Use Redis (Upstash free tier) for rate-limit state | At first app restart under attack |
| `cryptography` library imported at module top | 300-500ms import time | Lazy-import inside the signing function | Matters for serverless cold-starts; doesn't matter for long-running processes |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Logging the full request object including `Authorization` or future-private headers | Credentials leak to logs | Provide `safe_log(request)` helper; never log raw request in SDK code |
| Accepting `keyid` from request and trusting it | Key-confusion attack: attacker uses a key they control but claims to be a known operator's keyid | Always cross-check: keyid → directory → operator. Reject mismatches |
| No `nonce` on sensitive operations | Replay attacks possible inside the `expires` window | Document nonce as required for any directory-write operation; verify on the directory backend with a Redis-backed dedupe (1h TTL) |
| Trusting the `Date` header for clock-skew calculation when it isn't in the signature base | Attacker can rewrite Date to bypass expiration check | Require `created` parameter (signed) in addition to or instead of Date header |
| Allowing arbitrary URLs in `Signature-Agent` directory lookup | SSRF: attacker tricks verifier into fetching internal IPs | Whitelist URL schemes (https only), block private IP ranges in resolution, use a fetch-timeout (5s max) |
| No content-digest verification | Body tampering possible if content-digest is signed but not verified | Always verify content-digest matches actual body on the receiving side; document this responsibility for verifiers |
| TOFU on first key seen, no rotation handling | Attacker who briefly compromises a key can pin it forever | Always re-fetch the directory on `keyid` mismatch; cap pinning to 7 days max |
| Reserving the `operator` field with no claim verification | Trivial impersonation of major operators | Reserved name list + (v2) domain-ownership challenge |
| Storing private keys in environment variables and exposing process to debug endpoints | Process introspection leaks key | If using env-var storage, scrub from `os.environ` immediately after parsing |
| Public unauth bulk export of directory contents | Privacy harm even if data is "public" — enumerable target list for attackers | Rate-limit list endpoints; require pagination with cursor; no full dump endpoint |

---

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| `verify()` returns `bool` only | User can't debug why a signature failed | Return rich result: `VerifyResult(ok: bool, reason: str, details: dict)`; never bare bool |
| Cryptic errors like "signature verification failed" | User wastes hours guessing | Include the exact byte sequence the verifier reconstructed vs. expected; suggest most-likely cause ("did you include signature-agent?") |
| `inspect(url)` blocks for 5+ seconds because it fetches 6 different `.well-known` paths sequentially | User abandons the call | Concurrent fetches; per-fetch 2s timeout; partial results acceptable |
| No way to test signing locally without a remote verifier | User can't iterate offline | Ship `agentpassport.local_verify(request)` that uses the same code path the directory's verifier uses |
| Auto-generated key has random name; user doesn't know what the keyid is | User can't publish or reference the key | Print at generation: keyid (thumbprint), file path, exact CLI command to publish |
| Telling users to "enable Web Bot Auth on Cloudflare" without saying how (it's a manual submission process taking weeks) | Users believe SDK is broken when really they need to wait for Cloudflare review | Quickstart explicitly shows the Cloudflare submission flow with screenshots; warn about timing |
| Pre-flight inspector returns `allowed: True/False` | Oversimplifies — many real cases are conditional ("allowed but rate-limited" or "allowed for crawlers but not for ChatGPT-User") | Return structured policy; let the caller decide how to interpret |
| Different `inspect()` shape for Python vs TypeScript | Cognitive overhead, drift | Codify the shape in a JSON schema both SDKs validate against |

---

## "Looks Done But Isn't" Checklist

- [ ] **Ed25519 signing:** verify against IETF canonical test vectors (not just self-roundtrip). Without these, the SDK might be self-consistent but interop-broken.
- [ ] **Cloudflare interop:** integration test against `cloudflareresearch/web-bot-auth` or a hosted Cloudflare endpoint. "Verifies on our verifier" is not "verifies on Cloudflare."
- [ ] **AWS AgentCore interop:** at least a manual verification once per release; AgentCore profile may differ subtly.
- [ ] **Signature-Agent header:** verify in CI that the value is a quoted string (Structured Field) and `signature-agent` is in the component list.
- [ ] **Clock skew test:** test signing with system clock drifted ±60s; verify SDK rejects appropriately.
- [ ] **Key permission check:** test loading a key file with `0o644`; SDK must refuse with clear error.
- [ ] **Key repr safety:** test that `repr(key)` and `str(key)` and `pickle.dumps(key)` do NOT include private bytes.
- [ ] **TS/Python parity:** conformance test runner passes on both SDKs against the shared test-vectors file.
- [ ] **robots.txt edge cases:** test against (a) site that returns HTML for `/robots.txt`, (b) site with empty `/robots.txt`, (c) site with no `/robots.txt`, (d) site that returns 403 on `/robots.txt`, (e) site with malformed grammar.
- [ ] **`.well-known/*` HTML detection:** test against a SPA-catch-all that returns 200 + HTML for all paths.
- [ ] **Directory rate limits:** load test with 100 RPS to a free-tier endpoint; verify 429s served, not 500s.
- [ ] **Directory cost cap:** verify spending limit configured AND verify the read-only fallback works when limit is hit.
- [ ] **Domain auto-renewal:** confirmation email received from registrar showing 2+ year renewal scheduled.
- [ ] **2FA backup codes:** printed, location documented in private notes.
- [ ] **PyPI/npm trusted publisher:** test release pipeline runs end-to-end without manual auth.
- [ ] **Bus-factor pinned issue:** drafted, scheduled, moderators recruited and confirmed.
- [ ] **README 30s test:** show to 3 non-author developers; ask "what does this do?" Time to correct answer must be <30s.
- [ ] **Native English review:** at minimum the README + quickstart + 60s demo script.
- [ ] **Loom demo:** under 75 seconds, no filler words, shows install → import → working result.
- [ ] **Three real-user logos/quotes** before public launch.
- [ ] **Conformance canary:** GitHub Action runs daily and fails loudly on regression.
- [ ] **Dep upper bounds:** every direct dep has `<X.Y` cap.
- [ ] **uv lockfile committed.**
- [ ] **Frozen v1.x branch** documented as recommended pin.

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Cloudflare changes verifier, SDK breaks | LOW (if canary in place) | Canary opens issue → moderator backports profile change to frozen branch → trusted publisher releases hotfix |
| Cloudflare changes verifier, NO canary | HIGH | Discover via user complaints (weeks/months); rebuild trust |
| Private key leaked via log | CATASTROPHIC | Rotate key → revoke old key in directory → notify Cloudflare/affected verifiers → publish security advisory → audit all SDK versions for the leaking code path → release CVE |
| Domain `agentpassport.dev` expires | CATASTROPHIC | Domain may be hijacked within 24h of expiration; recovery is bidding on aftermarket. Prevention >>> recovery |
| Postgres major version upgrade fails on Supabase | MEDIUM | Restore from automated backup (Supabase 7-day default); verify backup before army leave |
| PyPI account locked (lost 2FA) | MEDIUM-HIGH | PyPI support recovery via paper backup codes; if codes lost, account is gone (no human appeal). Hence: paper backup, multiple copies |
| Spam registration flood overruns directory | LOW (if rate limits + spending cap) | Rate limit kicks in; spending cap prevents bill blowout; backlog cleared on return |
| RU card declined for hosting renewal | MEDIUM | Backup card on file; if both fail, infra goes down; recovery via friend with non-RU card |
| Issue backlog perception kills adoption | MEDIUM (if pinned status issue) | Pinned status communicates intent; moderators triage; auto-close stale; on return, batch-process |
| Dep major version breaks install | LOW (if upper bound pinned) | `pip install agentpassport>=1.0,<2` keeps existing users on a working line; fix on return |
| `Signature-Agent` quoting bug discovered post-launch | LOW (if patched fast) | Hotfix release; the bug is server-rejected, not silently-passing, so user discovery is fast |
| Operator impersonation reported | MEDIUM | Reserved-name list addition; manual review of registration; public security advisory; soft-delete the impersonation entry |
| TS SDK silently lagging Python SDK | MEDIUM | Conformance runner fails CI; new release blocked until both pass; no untrusted releases |

---

## Pitfall-to-Phase Mapping

Phases here map to the project's natural decomposition (see strategic memo's 8-week plan).

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1. Signature-Agent malformed | Phase 1 (Python SDK core) | CI integration test against Cloudflare reference verifier |
| 2. Wrong derived components | Phase 1 (Python SDK core) | Cloudflare-safe profile is default; advanced profile gated by explicit opt-in |
| 3. Clock skew + short expires | Phase 1 + Phase 4 (directory) | `/time` endpoint live; SDK `diagnose()` covers clock check |
| 4. Private key logged | Phase 1 | Pickling test, repr test, file-permission test in CI |
| 5. Key path conflicts | Phase 1 | Explicit XDG path; refuse-overwrite test |
| 6. TOFU vs directory confusion | Phase 1 (SDK) + Phase 4 (directory) | Two distinct API methods; documented threat model; immutable URLs in directory |
| 7. Cloudflare submission never approved | Phase 2 (CF integration docs) | Live demo agent submitted and approved BEFORE army leave |
| 8. robots.txt parser ambiguity | Phase 3 (inspector) | Test corpus covers HTML-200, empty, 403, malformed; uses protego not stdlib |
| 9. llms.txt overpromise | Phase 3 (inspector) | API returns soft-hint label; README disclaimer locked |
| 10. Python/TS API drift | Phase 1 + Phase 2 | Shared test vectors repo; conformance runner blocks releases |
| 11. Dependency rot during leave | Phase 5 (pre-leave hardening) | uv lockfile, upper bounds, scheduled CI, frozen branch — all present and tested |
| 12. Verifier behavior changes mid-leave | Phase 5 | Daily canary running; IETF watcher set up; moderators briefed |
| 13. RU payment lockout | Phase 0 + Phase 5 | No payment surface in v1; renewals funded for >18 months; backup card |
| 14. PyPI/npm publishing identity | Phase 5 | Trusted publisher live; backup 2FA codes documented; project email |
| 15. Directory cost / DoS | Phase 4 | Rate limits + spending cap + CDN in front |
| 16. Operator impersonation | Phase 4 | Reserved names + provenance display in v1 |
| 17. Non-native English docs | Every phase | Native English review per release; glossary file in repo |
| 18. README doesn't show value in 30s | Phase 5 (launch prep) | 3-developer 30s test; locked README template |
| 19. Issue backlog perception | Phase 5 | Pinned status, auto-labeling, moderators recruited, auto-close stale |
| 20. CF/AWS obsolescence in 6 months | Phase 0 (positioning) + Phase 3 (inspector moat) | Multi-verifier support shipped; inspector is the differentiator; positioning narrative drafted |

---

## Russia-Specific Pitfalls Summary

Called out explicitly per quality gate:

1. **OFAC IT-Services Determination (12 Sep 2024)** restricts US persons from providing IT services to RU-located persons. Affects: Stripe, GitHub Sponsors-style flows, and (debatably) any US-based hosting that requires KYC of the customer. **Hold:** v1 has no payment surface, period.
2. **Mir cards are blocked from international rails since 2022.** Only Visa/Mastercard cards from non-RU banks reliably work for international hosting. **Hold:** verify Railway/Fly.io accept the card on day 1; have backup card from a relative or past travel.
3. **GVA Capital $216M penalty (July 2025)** is a chilling-effect signal for any US entity processing payments from RU-domiciled operators. **Hold:** keep `agentpassport.dev` as a non-commercial public good; no donations, no tier.
4. **GitHub does NOT currently sanction Russia at the country level**, but enforcement could tighten. **Hold:** project email separate from personal; trusted publisher via OIDC reduces lock-in to one human.
5. **PyPI/npm don't have country sanctions**, but bias-flagging exists. **Hold:** project-scoped account, paper 2FA backup codes.
6. **Domain registrars vary**: Namecheap historically accepts RU cards; Cloudflare Registrar refuses many; Porkbun mixed. **Hold:** verify on registration; multi-year payment to limit exposure during army leave.
7. **No Stripe/Mercury/Brex** for any future SaaS revenue — even post-relocation, plan for Lemon Squeezy or Paddle.
8. **Russian-author signal in docs** is a non-trivial trust handicap — invest in native English review per release.

## Army-Leave-Specific Pitfalls Summary

Called out explicitly per quality gate:

1. **Dependency rot** (Pitfall 11) — pin upper bounds, lockfile, scheduled CI, frozen v1.x branch.
2. **Verifier behavior changes** (Pitfall 12) — daily canary GitHub Action posting to a webhook + auto-issue-opening.
3. **Domain expiration** — multi-year auto-renewal, backup card.
4. **PostgreSQL upgrades on managed host** — pin to specific Supabase major; pre-do the May 30 2026 GRANT migration before leave.
5. **2FA device loss** — paper backup codes, project email instead of personal.
6. **PyPI/npm publishing without you** — trusted publishers via GitHub Actions OIDC.
7. **Issue backlog perception** (Pitfall 19) — pinned status issue, auto-labeling, recruited moderators.
8. **Cost overruns from abuse** (Pitfall 15) — rate limits + hard spending caps that fail safe (read-only mode), not unsafe (down).
9. **TS SDK drift** — conformance runner blocks any release that fails parity.
10. **Cloudflare submission stalls** — submit a live demo agent and get it approved BEFORE leaving so the documented flow has a verified end-to-end example.
11. **Trust signal**: pinned README banner ("solo dev on military service until ~Nov 2026") plus designated security contact email — counterintuitively builds MORE trust than silence.

---

## Sources

**Web Bot Auth / RFC 9421:**
- [RFC 9421 - HTTP Message Signatures (IETF)](https://datatracker.ietf.org/doc/html/rfc9421)
- [Cloudflare bot docs — Web Bot Auth reference](https://developers.cloudflare.com/bots/reference/bot-verification/web-bot-auth/)
- [Cloudflare bot docs — Verified bots program](https://developers.cloudflare.com/bots/concepts/bot/verified-bots/)
- [Cloudflare bot docs — Signed agents](https://developers.cloudflare.com/bots/concepts/bot/signed-agents/)
- [cloudflare/web-bot-auth (GitHub)](https://github.com/cloudflare/web-bot-auth)
- [cloudflareresearch/web-bot-auth (GitHub)](https://github.com/cloudflareresearch/web-bot-auth)
- [Cloudflare blog — Forget IPs: cryptography to verify bot and agent traffic](https://blog.cloudflare.com/web-bot-auth/)
- [Cloudflare blog — Message Signatures part of Verified Bots Program](https://blog.cloudflare.com/verified-bots-with-cryptography/)
- [Cloudflare community — Web Bot Auth Signature Validation Failure](https://community.cloudflare.com/t/web-bot-auth-signature-validation-failure/854577)
- [draft-meunier-http-message-signatures-directory-04 (IETF)](https://datatracker.ietf.org/doc/html/draft-meunier-http-message-signatures-directory)
- [IETF webbotauth slides — Replay attacks on HTTP Signatures](https://datatracker.ietf.org/meeting/124/materials/slides-124-webbotauth-v2-replay-attacks-on-http-signatures-00)
- [Stytch — How to implement Web Bot Auth](https://stytch.com/blog/how-to-implement-web-bot-auth-signing/)
- [Akamai — Web Bot Authentication](https://www.akamai.com/blog/security/redefine-trust-web-bot-authentication)
- [Fingerprint — Web Bot Auth Guide](https://fingerprint.com/blog/web-bot-auth-guide/)
- [Victor on Software — Understanding HTTP message signatures](https://victoronsoftware.com/posts/http-message-signatures/)

**Implementations & libraries:**
- [pyauth/http-message-signatures (GitHub)](https://github.com/pyauth/http-message-signatures)
- [pyauth/requests-http-signature (GitHub)](https://github.com/pyauth/requests-http-signature)
- [yaronf/httpsign (Go, RFC 9421)](https://github.com/yaronf/httpsign)
- [olipayne/guzzle-web-bot-auth-middleware (PHP example)](https://github.com/olipayne/guzzle-web-bot-auth-middleware)
- [stytchauth/web-bot-auth-example](https://github.com/stytchauth/web-bot-auth-example)

**robots.txt / ai.txt / llms.txt:**
- [Paul Calvano — AI Bots and Robots.txt (2025-08)](https://paulcalvano.com/2025-08-21-ai-bots-and-robots-txt/)
- [ai-robots-txt/ai.robots.txt (GitHub list)](https://github.com/ai-robots-txt/ai.robots.txt)
- [BuzzStream — News Sites Blocking AI Crawlers 2025](https://www.buzzstream.com/blog/publishers-block-ai-study/)
- [AEO Engine — llms.txt Zero Usage 2026](https://aeoengine.ai/blog/llms-txt-zero-usage-ai-bots-ignore)
- [aeo.press — State of llms.txt in 2026](https://www.aeo.press/ai/the-state-of-llms-txt-in-2026)
- [ALLMO — llms.txt for AI Search Report 2026](https://www.allmo.ai/articles/llms-txt)
- [Cookie Script — Beyond Robots.txt: AI.txt and LLMs.txt](https://cookie-script.com/guides/beyond-robots-txt-implementing-ai-txt-and-llms-txt-for-purpose-based-scraping-control)

**OSS distribution & documentation:**
- [Stagehand vs Browser Use comparison (Skyvern blog)](https://www.skyvern.com/blog/browser-use-vs-stagehand-which-is-better/)
- [Stagehand v3 launch (Browserbase)](https://www.browserbase.com/blog/stagehand-v3)
- [Socket.dev — The Unpaid Backbone of Open Source](https://socket.dev/blog/the-unpaid-backbone-of-open-source)
- [HeroDevs — OSS Tech Stack That Won't Bite in 18 Months](https://www.herodevs.com/blog-posts/how-to-build-an-oss-tech-stack-that-wont-bite-you-in-18-months)
- [arxiv 2508.02497 — LLM-Driven Documentation Translation in OSS](https://arxiv.org/html/2508.02497v1)

**Russia / OFAC / sanctions:**
- [OFAC — Russia-related Sanctions](https://ofac.treasury.gov/sanctions-programs-and-country-information/russia-related-sanctions)
- [Hodder Law — 2024 Russian Sanctions Impact on Tech Companies](https://hodder.law/new-russia-sanctions-2024/)
- [GitHub — Trade Controls policy](https://docs.github.com/en/site-policy/other-site-policies/github-and-trade-controls)
- [arxiv 2404.05489 — Impact of Sanctions on GitHub Developers](https://arxiv.org/html/2404.05489v1)
- [Sidley Austin — 2025 US Sanctions Enforcement Takeaways](https://www.sidley.com/en/insights/newsupdates/2026/02/five-key-takeaways-from-2025-us-sanctions-enforcement)
- [Mir (payment system) — Wikipedia](https://en.wikipedia.org/wiki/Mir_(payment_system))

**Managed hosts / unattended operation:**
- [Supabase — Upgrading documentation](https://supabase.com/docs/guides/platform/upgrading)
- [Supabase Changelog (May/Oct 2026 GRANT change)](https://supabase.com/changelog)
- [Supascale — Upgrading Self-Hosted Supabase](https://www.supascale.app/blog/upgrading-selfhosted-supabase-a-complete-version-migration-g)
- [Railway pricing](https://railway.com/pricing)
- [AWS Developer Tools — Clock-skew correction](https://aws.amazon.com/blogs/developer/clock-skew-correction/)

**AWS Bedrock AgentCore (competitive context):**
- [AWS — AgentCore Identity OBO support (April 2026)](https://aws.amazon.com/about-aws/whats-new/2026/04/amazon-bedrock-agentcore/)
- [AWS — AgentCore new features (April 2026)](https://aws.amazon.com/about-aws/whats-new/2026/04/agentcore-new-features-to-build-agents-faster/)
- [Cloudflare — Agents Week 2026 review](https://blog.cloudflare.com/agents-week-in-review/)

**Identity / impersonation:**
- [OpenClaw — Agent Passport: Identity Verification for AI Agents](https://openclawradar.com/article/agent-passport-identity-verification-ai-agents)
- [Stytch — AI agent fraud attack vectors](https://stytch.com/blog/ai-agent-fraud/)
- [Resilient Cyber — Identity Is the Agentic AI Problem Nobody Has Solved](https://www.resilientcyber.io/p/identity-is-the-agentic-ai-problem)

**Project context:**
- `/Users/leonid/Documents/coding/Vibecoded/YC/.planning/PROJECT.md`
- `/Users/leonid/Documents/coding/Vibecoded/YC/strategic_memo_ru.md`

---

*Pitfalls research for: Agent Identity & Pre-flight Policy Toolkit*
*Researched: 2026-05-03*
