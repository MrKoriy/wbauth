# wbauth

> Web Bot Auth (RFC 9421) for AI agents — signed identity + pre-flight site policy.

**Pre-1.0.** API will lock at the v1.0 tag. Do not depend on internals yet.

## Layout

- `python/` — Python SDK (`pip install wbauth`)
- `typescript/` — TypeScript SDK (`npm install wbauth`)
- `directory/` — TypeScript Cloudflare Worker (zero-billing JWKS directory; Phase 3)
- `spec/test-vectors/` — cross-language test vectors (RFC 9421 + Web Bot Auth)
- `docs/` — Astro Starlight docs site (Phase 5)

## License

Apache 2.0 — see `LICENSE`.
