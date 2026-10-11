# Maintainer Service & Long-Term Support Notice

> **Current Status:** Frozen / Active LTS  
> **Target Release:** v0.1.x / v1.0.x  
> **Expected Full Maintainer Return:** Late 2027  

---

## 1. Context & Compatibility Commitment

The core author and maintainer of `wbauth` ([Leonid Kutlin / @MrKoriy](https://github.com/MrKoriy)) is currently fulfilling mandatory military service duties through late 2027.

To ensure that teams relying on `wbauth` for RFC 9421 bot authentication and policy inspection face zero unexpected disruptions, this repository follows a **Strict Frozen-Contract Policy**:

1. **RFC 9421 & Web Bot Auth Parity**: The cryptographic primitives (Ed25519 signer, JWKS export, RFC 7638 thumbprint calculation) are verified against immutable golden test vectors in `spec/test-vectors/`. These vectors guarantee zero cross-language drift between Python (`wbauth`) and TypeScript (`wbauth`).
2. **Zero Breaking Changes on `main`**: No backward-incompatible changes will be merged into the `v0.1.x` and `v1.x` release series.
3. **Zero Dynamic Cloud Dependencies for Core**: `wbauth.inspect(url)` and the signing adapters operate fully in-process without hard runtime dependencies on proprietary gateways.

---

## 2. CI/CD Canaries & Automated Health Checks

The project includes scheduled GitHub Actions workflows to catch external ecosystem changes:
- **Daily Cloudflare Research Verifier Canary**: Automatically runs against Cloudflare's research verifier endpoint to detect upstream HTTP signature specification shifts.
- **Bi-weekly Package Install Canary**: Verifies that new versions of underlying dependencies (`httpx`, `playwright`, `cryptography`, `vitest`) do not break clean installations.

---

## 3. Reporting Critical Issues / Vulnerabilities

If you discover a critical security vulnerability or an RFC compliance break:
- Please open a GitHub Issue with the label `[Security]` or `[Spec Drift]`.
- Designated community triagers and automated CI bots monitor the issue tracker for critical regressions.

---

*“Code built to survive unattended, from the bare metal to the autonomous agent.”*
