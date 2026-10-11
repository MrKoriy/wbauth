# Changelog

## 0.3.0

Audit release (Oct 2026). Every fix below has a regression test
(`python/tests/test_audit_2026.py`, `typescript/tests/audit-2026.test.ts`,
`directory/tests/domain.test.ts`).

### Security
- **Redirects no longer leak signatures.** httpx `auth=` flows follow redirects internally, and native `fetch` forwards custom headers, so hop 2 received hop 1's signature (invalid there, replayable at hop 1 for 60 s). New `signed_client()` / `signed_async_client()` / `SigningTransport` re-sign every hop; `WebBotAuth` warns (`RedirectNotSignedWarning`) when it sees an unsigned hop. TS `createSignedFetch` now follows redirects itself, re-signing each hop, rewriting method/body per the fetch spec and dropping `Authorization`/`Cookie` across origins (`maxRedirects` option).
- **Directory: domain impersonation.** Registrations now record `domain_verified` (the `signature_agent_url` must be the directory-hosted JWKS or publish the registered key). Exposed in all read endpoints. Run migration `0005_domain_verification.sql` before deploying.
- **Inspector SSRF guard:** redirects from a public origin to loopback/private/link-local/reserved IPs, `localhost`, or non-HTTP schemes are refused.
- Signers reject `bool` and windows above 3600 s; bodies on any method (DELETE, QUERY, …) are bound via `content-digest`.

### Fixed
- `@authority` is RFC 9421-normalized in Python (no userinfo / default port) — `https://host:443/` signatures failed verification at Cloudflare and differed from TS.
- robots.txt / ai.txt / llms.txt with a UTF-8 BOM: the first group was ignored (a `Disallow: /` became `allowed`).
- `http://` targets and custom ports were probed over `https://`; http and https no longer share cache entries.
- ai.txt restrictions are path-scoped when they name paths; `*`, `+`, `•` and `-item` bullets and inline `# comments` are parsed.
- `Cache-Control: private` no longer disables the (client-side) policy cache; `no-store` entries are never kept for revalidation.
- README installed a non-existent `wbauth` distribution (the dist is `wbauth-sdk`); `uv.lock` was stale after the rename, so `uv sync --locked` failed in CI.
- Default User-Agent is `wbauth/<version>` (was hard-coded `wbauth/0.1`).
- CLI tests no longer require `uv` on PATH.
- Directory: challenge and submit have separate daily budgets (a registration used to cost 2 of 10); IPv6 limited per /64.

### Added / Performance
- Python signer builds the RFC 9421 base directly: ~2.3× faster (121 → 53 µs per GET), byte-identical to `http-message-signatures` (property test).
- Concurrent `inspect()` calls share in-flight fetches; ETag / Last-Modified revalidation (304); `save_cache()` / `load_cache()` persistence.
- `wbauth inspect --format table` (colored per-source breakdown) and `--cache PATH`.
- Directory web page (`/`, search, verified marks) and `/badge/{kid}.svg`.
- CI: `cross-language.yml` — Python-signed requests verified by Cloudflare's TS verifier and vice versa (randomized); hypothesis fuzzing of parsers and verdict engine.

## 0.2.0

### Breaking
- **npm package renamed to `wb-auth`.** CommonJS entry is now `dist/index.cjs` (ESM `dist/index.js`); use the `exports` map.
- **Policy verdicts follow RFC 9309:** robots.txt 4xx (except 429) = no restriction; 429/5xx/timeouts/network errors = `forbidden`.
- Python: Playwright moved to the optional extra `wbauth[playwright]`.
- Directory Worker: `/register/submit` must sign `content-digest` (matching the body) and send a `Signature-Agent` equal to `signature_agent_url`; `kid` must equal the RFC 7638 thumbprint of every key. Run migration `0004_challenges_keyed_by_nonce.sql` before deploying. `?all=true` on `/agents` was removed.

### Security
- Directory: fixed agent takeover (kid not bound to key), replayable/raced challenges (now keyed by nonce and consumed atomically), unsigned bodies.

### Added
- Python: `signed_session()` / `WebBotAuthTransport` re-sign redirect hops (`requests` did not re-run auth on redirects); `inspect(url, user_agent=, client=)`; `wbauth inspect --user-agent`; `RobotsResult.crawl_delay`; `[http2]` extra.
- TS: `applyTo(page, identity, { hosts, shouldSign })`, custom `fetch` option, `fromTestKey(url, { userAgent })`.
- Both: host scoping for Playwright, identity `User-Agent` replaces library defaults.
- Directory: 60 s edge cache for reads with purge on re-registration; stricter schema validation.
- CI: Node 20/22/24 and Python 3.11–3.13 matrices, locked `uv`, directory job, tag-vs-version release check, npm provenance.

### Fixed
- Signers reject non-positive expiry and strip stale signature headers; body without `Content-Digest` is rejected.
- `createSignedFetch` preserves `signal`, `redirect`, `credentials`, etc.
- Policy cache honours `max-age` per entry and caches negative results; robots.txt cached per host and evaluated per path/UA; response size caps.
