# spec/test-vectors/

Cross-language test vectors for wbauth's RFC 9421 + Web Bot Auth signer.

## Format

Each vector is a directory with two files:

- `input.json` — the inputs (request, identity, signing params)
- `expected.json` — the expected `Signature-Input`, `Signature`, `Signature-Agent` strings + computed `kid`

See `.planning/phases/01-foundation-cryptographic-root/01-RESEARCH.md` §5
for the full schema and the canonical six initial vectors.

## Why byte-equality works

Ed25519 signing is deterministic: given the same private key + message bytes,
the signature is identical every time. With fixed `created`/`expires`/`nonce`
and the publicly-known RFC 9421 Appendix B.1.4 test key, the produced
`Signature-Input` and `Signature` headers are reproducible across:

- Multiple Python runs (pytest)
- Multiple TypeScript runs (vitest)
- Multiple language implementations (the cross-language oracle gate)

## Status

- Plan 02 (this plan): scaffold this README only.
- Plan 04: author the six initial vectors and wire them into pytest + vitest.
