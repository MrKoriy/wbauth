# Security policy

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

Report privately via GitHub: **Security → Report a vulnerability** on
[MrKoriy/wbauth](https://github.com/MrKoriy/wbauth/security/advisories/new).
Include affected component (`python/`, `typescript/` / npm `wb-auth`, `directory/`), version,
reproduction steps and impact. We aim to acknowledge within 72 hours.

## Supported versions

| Version | Supported |
|---|---|
| 0.2.x | ✅ |
| < 0.2 | ❌ (directory registration could be hijacked; upgrade) |

## Scope

In scope: signature generation/verification, key handling, the policy engine, and the
directory Worker (registration, challenge handling, caching).
Out of scope: issues that require a compromised local machine or a leaked private key.
