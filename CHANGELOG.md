# Changelog

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
