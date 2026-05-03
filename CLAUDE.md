<!-- GSD:project-start source:PROJECT.md -->
## Project

**Agent Identity & Policy Toolkit**

OSS-первый Python+TypeScript toolkit, который даёт AI-агентам две вещи: (1) **identity** — подписанные HTTP-запросы по IETF Web Bot Auth, чтобы их перестали блокировать Cloudflare/AWS/Akamai как анонимных ботов, и (2) **pre-flight policy** — структурированную картину того, что им разрешено и поддерживается на конкретном сайте (robots.txt, ai.txt, llms.txt, MCP/ACP/AP2 endpoints, rate limits) до первого запроса. Дополняется бесплатным hosted-каталогом `agentpassport.dev`, где любой агент публикует свой identity, а сайты — верифицируют.

Целевые пользователи: разработчики агентных фреймворков и кастомных агентов (Browser Use, Stagehand, Skyvern, Playwright + LLM, OpenAI Agents SDK), которым нужно обходить CAPTCHA-блокировки и не сжигать токены на сайты, которые их явно не пускают.

**Core Value:** **AI-агенты получают идентичность и знают свои права на сайте — до того, как сделают первый запрос.** Если ничего другое не работает, эти две вещи (signed identity + pre-flight policy) должны работать в одну строку импорта.

### Constraints

- **Tech stack — Python**: Native-quality. Основной SDK на Python, FastAPI для directory backend, Postgres/Supabase для хранения. Нативное окружение разработчика.
- **Tech stack — TypeScript**: Слабее, но обязательно для покрытия Stagehand/Browser Use экосистемы. Делегируется агентам с тщательной верификацией.
- **Tech stack — Cloud**: Hosted directory на Railway или Fly.io (принимают карты РФ в 2026). НЕ Vercel.
- **Биллинг**: Нет в v1. Если будет добавлен после армии — Lemon Squeezy или Paddle, не Stripe (закрыт для KYC только-РФ).
- **Timeline — режим разработчика**: Чередование 2-3 ч/день (рабочая неделя) и 8 ч/день (больничный). Окно ~6 недель до призыва.
- **Timeline — pre-army**: Цель — задокументированный, стабильный, self-contained релиз, который не требует hot-fixes в первые 6+ месяцев отсутствия мейнтейнера.
- **Параллелизация**: Активно использовать делегацию задач между агентами разработки (Python SDK / TS SDK / directory backend / docs+landing — параллельные потоки).
- **Юрисдикция**: Релокация невозможна. Никаких US-инкорпораций, никаких Stripe payouts. Чистый OSS под Apache 2.0; директория хостится на сервисе, принимающем РФ-карты.
- **Distribution**: GitHub + HN + X + Reddit (r/LocalLLaMA, r/MachineLearning) + Browser Use Discord + MCP CWG Discord. Всё на native-quality English; Claude/GPT-5 для polish, не fake.
- **Maintenance после публикации**: Должен пережить армейский перерыв. Это значит: минимум moving parts в production, экстремально хорошая документация, никаких CI/CD pipelines, требующих ручного вмешательства, директория на managed hosting с автообновлением.
- **Безопасность**: Web Bot Auth включает Ed25519 keys; должна быть строгая secret-management hygiene в SDK (никаких логов с private keys, чёткие docs о хранении).
- **Этика**: Идентичность — это про честность («вот кто я, вот что я хочу»), не про anti-detection. Никаких stealth-фич.
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## Executive Position
## Recommended Stack
### Core Technologies — Python SDK
| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| **Python** | 3.11 (target floor) / 3.12 (dev) | SDK language | 3.11 is the lowest version still receiving security fixes through Oct 2027 — critical for "ship and forget." `http-message-signatures` 2.0.1 requires ≥3.10; 3.11 gives you another year of headroom over 3.10. 3.12/3.13 fine for dev, but don't make 3.12+ a floor — you'll lock out users. |
| **`http-message-signatures`** | 2.0.1 (Jan 2026) | RFC 9421 implementation | The canonical pyauth maintainer's RFC 9421 implementation. Same author as `requests-http-signature`. Apache 2.0. Active. Don't roll your own. **Confidence: HIGH.** |
| **`requests-http-signature`** | latest (≥3.0.0 line) | Drop-in `requests` auth class with Ed25519 | `algorithms.ED25519` is built-in. Apache 2.0. Same maintainer as the core lib. This is your "users on `requests`" path. **Confidence: HIGH** (Ed25519 explicitly documented in repo). |
| **`cryptography`** | 46.x (PyCA) | Ed25519 keygen, JWK conversion | Default crypto for the Python ecosystem; `Ed25519PrivateKey.generate()` and PEM/JWK export are first-class. Already a transitive dep of nearly everything. PyCA-maintained. **Confidence: HIGH.** |
| **`httpx`** | 0.28.x | Async HTTP client + custom Auth flow | First-class custom `Auth` subclass (`auth_flow(request)` + `requires_request_body`) is the cleanest place to plug Ed25519 signing. Used by FastAPI's TestClient too — single client lib across SDK and tests. **Confidence: HIGH.** |
| **`pydantic`** | 2.x (≥2.9) | Schema validation for inspector return types | Fast, types are FastAPI-native, well-known. v2 is ~50× faster than v1; do NOT support v1. |
### Core Technologies — TypeScript SDK
| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| **Node** | 20 LTS (floor) / 22 (dev) | Runtime baseline | Node 20 receives security fixes through Apr 2026 → extended to 2027 in maintenance; Node 22 is the active LTS in 2026. Don't require 22+; lots of agent frameworks pin 20. |
| **`web-bot-auth`** (Cloudflare) | latest npm release | RFC 9421 + Web Bot Auth signing | This is **the** reference TS implementation, written by Cloudflare Research. Exports `signatureHeaders` / `signerFromJWK` / `verify` / `verifierFromJWK`. Used in Cloudflare's own examples for Puppeteer + Workers. Don't fork; depend. **Confidence: HIGH.** |
| **`http-message-sig`** | latest | Lower-level RFC 9421 (if `web-bot-auth` is too opinionated) | Cloudflare also publishes this as a separate package in the same monorepo. Use only if you need raw signature primitives outside the Web Bot Auth shape. |
| **`jose`** (panva) | 5.x | JWK / JWKS handling, key gen | Most-used JOSE lib in Node, isomorphic, no native deps. Stytch's reference Web Bot Auth blog uses it; Cloudflare's examples use it. **Confidence: HIGH.** |
| **Native `fetch`** | — | HTTP client | Built into Node 18+. No `axios` dependency. Sign by computing headers and passing them to `fetch(url, { headers })`. Zero install footprint matters for "drop-in" adoption. |
| **`zod`** | 3.x | Runtime schema validation for inspector return types | TypeScript ecosystem default. Mirrors Pydantic on the Python side. |
### Core Technologies — Directory Backend
| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| **FastAPI** | 0.118+ (track latest 0.12x as of mid-2026) | HTTP API framework | Native to your stack, async-first, OpenAPI auto-gen, TestClient lets you write CI tests with zero infra. **Confidence: HIGH** (Context7 confirms 0.118.2 / 0.122.0 / 0.128.0 series). |
| **Uvicorn** | 0.30+ | ASGI server | Standard FastAPI runtime. Single worker is fine for a directory at v1 scale. |
| **SQLite + WAL mode** | bundled | Storage | Single file on a persistent volume. No connection pool, no separate process, no managed-service bills, no version upgrades during army leave. Easily handles 100k+ JWKS records and a few req/sec lookup load. **This is the single highest-leverage maintenance-burden decision in the project.** |
| **`aiosqlite`** | 0.20+ | Async SQLite driver | Use only if you want the API itself async; the directory is read-heavy and either sync (with `asyncio.to_thread`) or async-via-aiosqlite is fine. |
| **`SQLAlchemy`** | 2.0 (core only, optional) | If you outgrow raw SQL | Use the 2.0 Core API (not the legacy ORM mode) only if it makes migrations cleaner. For a JWKS directory, **plain SQL with `sqlite3` stdlib + a 50-line repo file is more honest** and easier to read after 6 months away. |
| **`pydantic-settings`** | 2.x | Env var → config | Loads `.env` once at boot. Avoid runtime config files. |
### Core Technologies — Hosting & Distribution
| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| **Fly.io** | — | Directory backend hosting | Has a real `volumes` primitive for SQLite persistence. Single `fly.toml`, no CI required to redeploy. Free tier (3 shared-cpu-1x VMs + 3 GB volumes) covers v1 directory load comfortably. **Caveat — see "Russia card availability" section below; this is not a confirmed-works recommendation, only a confirmed-architecturally-fits one.** |
| **Railway** | — | Alternative directory backend hosting | Simpler DX than Fly, but persistent disk is bound to the service and Postgres is a separate billable add-on. Use if Fly billing fails for you. |
| **GitHub Pages** | — | Docs site hosting | Free, no expiring billing, no CDN to renew, served from your repo. The single most "army-leave-proof" hosting choice in the entire stack. **Confidence: HIGH.** |
| **PyPI + npm** | — | Package distribution | Both work fine from RU IPs for publishing (the registries don't sanction publishers), and global users install over CDN. Set up `trusted-publishers` on PyPI so you don't manage long-lived API tokens that expire mid-army. |
### Core Technologies — Docs Site
| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| **Astro** | 5.x | Static site framework | Outputs pure static HTML; no Node runtime in production; builds reproducibly years later. Active development, no maintenance-mode flag. |
| **Starlight** | 0.30+ | Docs theme on Astro | Out-of-box: search (Pagefind, client-side, no service), dark mode, sidebar, i18n, TypeScript types, Markdown + MDX. The `@astrojs/starlight` theme is maintained by the Astro core team — same governance as the framework, low bus factor. **Confidence: HIGH.** |
| **Pagefind** | 1.x | Search index | Generated at build time, served as static JSON; zero search service to keep alive. Bundled into Starlight by default. |
| **`actions/deploy-pages@v4`** | — | CI deploy | Single GitHub Action workflow file; no third-party CI. |
### Supporting Libraries
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **`reppy`** or **stdlib `urllib.robotparser`** | — | robots.txt parsing | Inspector module — robots.txt parsing. `urllib.robotparser` is in the stdlib and zero-maintenance; use it unless you need the more permissive parsing of `reppy`. |
| **`tenacity`** | 9.x | Retries on directory lookup | Wrap network calls in the inspector with exponential backoff. Standard, well-maintained. |
| **`structlog`** | 24.x | Structured logging | JSON logs out of the box for the directory backend; works with stdlib `logging`. Don't pick a SaaS logger (Datadog, Sentry-as-default) — they are exactly the kind of thing that breaks while you're away. Use the platform's built-in log viewer. |
| **`python-dotenv`** | 1.x | Local .env loading | Already a transitive dep through pydantic-settings. |
| **`vitest`** | 2.x | TS unit tests | Faster than Jest, native ESM, zero config for TS. Maintained by the Vite team. |
| **`tsup`** | 8.x | TS build for npm | Bundles to ESM + CJS + .d.ts in one command. Avoids a hand-written tsconfig matrix. |
| **`@playwright/test`** | latest | E2E for inspector against live test pages | Only for occasional manual runs — **do NOT** put live-network Playwright tests in CI; they will break unattended. |
### Development Tools
| Tool | Purpose | Notes |
|------|---------|-------|
| **`uv`** (Astral) | Python project + dep manager | Replaces pip + venv + pip-tools. Lockfile-driven, deterministic installs, ~10× faster. Stable as of late 2025. Use `uv sync` in CI for reproducible builds. |
| **`ruff`** | Python lint + format | Replaces flake8 + black + isort. Ruff format is now stable. One tool, one config. |
| **`pyright`** or `mypy` | Python type-check | Pyright (Microsoft) is faster and matches what most agent-framework devs already run via VS Code. |
| **`pnpm`** | Node package manager | Smaller `node_modules`, deterministic lockfile, monorepo-friendly if you eventually colocate the TS SDK with examples. |
| **`biome`** | TS lint + format | One binary, replaces ESLint + Prettier. Same one-tool philosophy as Ruff. |
| **`pytest`** + `pytest-anyio` | Python tests | Use `anyio` not `asyncio` plugin — FastAPI's recommended async test setup. |
| **`pytest-httpx`** | Mock httpx calls in tests | Lets you assert exactly what signature headers were emitted without hitting real endpoints. **Critical for deterministic CI.** |
| **GitHub Actions** | CI | Single `ci.yml` per repo — lint + type + unit tests + build + (on tag) publish. No third-party CI. |
| **Dependabot or Renovate** | Dep updates | Renovate is more configurable; Dependabot is built into GitHub and zero-config. **Recommend Dependabot** for the army-leave window: simpler, fewer moving parts, won't open 200 PRs. |
## Installation
# === Python SDK (uv) ===
# === Directory backend (uv, separate package) ===
# === TypeScript SDK (pnpm) ===
# === Docs site (npm — one-time, never touch again) ===
## Alternatives Considered
| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| `http-message-signatures` (pyauth) | Roll your own RFC 9421 | Never. The spec is subtle (signature base canonicalization, derived components, content-digest). 2.0.1 is mature; don't reinvent. |
| `cryptography` (PyCA) for Ed25519 | `PyNaCl` | Use PyNaCl only if you also need libsodium's box/secretbox. For Ed25519 alone, `cryptography` is the more universal dependency and avoids C-extension build pain on some platforms. PyNaCl is ~10–20× faster but you do not have a perf bottleneck on signing one HTTP request. |
| `cryptography` for Ed25519 | stdlib `cryptography`-free Ed25519 (`pure25519`) | Don't. Pure-Python Ed25519 is slower and less audited; `cryptography` ships everywhere. |
| `web-bot-auth` (Cloudflare) | `@misskey-dev/node-http-message-signatures` | Misskey's lib is also active and used in ActivityPub. Use it only if `web-bot-auth` ever stops being maintained — but Cloudflare has clear strategic incentive (it's their own verifier ecosystem). |
| `web-bot-auth` (Cloudflare) | `dhensby/node-http-message-signatures` | Also fine, RFC-compliant. Cloudflare's package is preferred because it bakes in the Web Bot Auth flavor (Signature-Agent header, JWKS thumbprint key IDs, debug endpoints). |
| FastAPI | Litestar | Litestar is faster and arguably nicer DX, but FastAPI is the boring-stack default and your users already know it. Lower bus factor for you = better. |
| FastAPI | Starlette directly | Use Starlette only if you find FastAPI's Pydantic-based response model is overhead. For a 4-endpoint directory, FastAPI is fine. |
| SQLite + volume | Postgres (managed) | Switch only when you cross any of: (a) >1 write/sec sustained, (b) need >1 region, (c) need JSON GIN indexes on agent metadata search. None of these apply to v1. |
| SQLite + volume | Supabase | Supabase = Postgres + Auth + Storage + Realtime — overkill. The Auth/Realtime parts are exactly the kind of "managed dependency that has a free-tier policy change" that breaks unattended projects. |
| Fly.io | Render | Render dropped its free tier for web services in late 2024 and is now $7/mo minimum — fine but a recurring bill while you're away. |
| Fly.io | Hetzner Cloud | Hetzner explicitly cannot contract with Russian-postal-address customers post-sanctions. Disqualified. |
| Fly.io | Yandex Cloud / Selectel | Russia-domiciled hosting — works fine for paying *from* Russia, but creates "this OSS project is Russia-hosted" optics that may matter for adoption signals (Cloudflare/AWS engineers checking out the project might balk). Use as **fallback** if Fly+Railway both refuse cards; otherwise prefer non-RU. |
| Astro Starlight | MkDocs Material | Material entered maintenance mode in Nov 2025, Insiders repo deleted May 1 2026. Successor "Zensical" not proven. Don't start a new project on a tool whose primary maintainer just stepped back. |
| Astro Starlight | Docusaurus | Docusaurus works fine but is heavier (React runtime, more config). Starlight is purpose-built for docs and ships less. |
| Astro Starlight | Plain GitHub README + a few `/docs` markdown files | Honestly viable for v1. Your docs are quickstart + API reference + FAQ — three pages. Starlight is the "professional polish" upgrade; consider deferring it until week 5 if time pressure appears. |
| GitHub Pages | Cloudflare Pages | Cloudflare Pages is also great but adds a vendor account that needs maintenance. GitHub Pages is already where your code lives. |
| `uv` | Poetry / pipenv / hatch | All work; `uv` is dramatically faster, simpler, and Astral's stewardship is currently unrivaled in the Python tooling space. |
## What NOT to Use
| Avoid | Why | Use Instead |
|-------|-----|-------------|
| **Stripe** (any role) | Closed for KYC-only-RU founders since 2022; processing payments through Stripe from RU triggers OFAC concerns. | No billing in v1. If billing later: **Lemon Squeezy** or **Paddle** as merchant-of-record (handle VAT/sales tax + payouts to non-RU bank). |
| **Vercel** | Has dropped Russia-card payment historically; also, deploys mutate frequently and can break unattended apps. | Fly.io / Railway / GitHub Pages depending on workload. |
| **Heroku** | No free tier since 2022; minimum $5/mo per dyno; Salesforce ownership = unpredictable pricing. | Fly.io. |
| **Supabase / Firebase / PlanetScale** | "Managed" means policy/pricing changes can brick your app while you're gone. PlanetScale already killed its free tier in 2024. | SQLite on a Fly volume. |
| **Datadog / New Relic / Honeycomb** | Per-host or per-event billing that can quietly run up to triple-digits. Free tiers exist but require periodic action to keep alive. | Platform built-in logs (Fly's `fly logs`) + occasional `structlog`-emitted JSON. Add **Sentry free tier** only if you want crash reporting — it's the one observability tool benign enough to leave running. |
| **MkDocs Material** (new project) | Maintenance mode Nov 2025; Insiders deleted May 2026. | Astro Starlight. |
| **Docusaurus i18n / versioning features** (if you do pick Docusaurus) | These features generate a lot of duplicated content; if you can't maintain translations for 6 months they go stale and look abandoned. | Pick English-only, no version dimension, until v2. |
| **Pydantic v1** | EOL'd; Pydantic v2 is 50× faster and is what FastAPI ≥0.100 expects. | Pydantic v2 strictly. |
| **`requests`** (as your *primary* SDK HTTP client) | Sync only, no `Auth` async story, smaller maintenance team than httpx. | `httpx` as primary; ship a `requests-http-signature` integration as a thin alias for users on legacy stacks. |
| **`axios` / `node-fetch`** | Native `fetch` is in Node 20+. Adding axios = another dep your users don't want forced on them. | Native `fetch`. |
| **Long-running CI integration tests against live websites** | They will flake while you're in the army; Cloudflare/AWS will respond differently month-to-month; CAPTCHA pages change. | Mocked tests in CI (`pytest-httpx`, `vitest` mocks). Run live integration tests **manually** before each release tag. Document them as `make smoke-test` not as CI. |
| **`asyncio` test mode in `pytest-anyio`** when FastAPI suggests it differently | Mismatch causes silent test skips. | Follow FastAPI's published anyio pattern exactly. |
| **GPG-signed releases / commit signing as required policy** | Signing key expiration mid-army-leave will silently break releases. | Use Sigstore-backed PyPI Trusted Publishers (no key to expire) and unsigned commits. |
| **Any package manager that requires periodic license/account reauth** (some private registries, Snyk, etc.) | Self-explanatory. | npm + PyPI public registries only. |
## Russia Card Availability — Hosting Reality Check
| Provider | Confirmed Status | Source Strength | Action |
|----------|------------------|-----------------|--------|
| **Hetzner** | **Will not contract with Russian-postal-address customers** post-sanctions. | HIGH (their docs + multiple LowEndTalk threads). | Do not use. |
| **DigitalOcean** | Accepts Visa/MC/Amex/Discover/UnionPay/JCB/Diners. **Mir not listed.** Russia VAT raised to 22% in 2026 → service still operating to RU. UnionPay-issued cards from RU friendly banks may work. | MEDIUM (their docs list cards, no policy on RU specifically). | Test before depending on it. |
| **Vercel** | Stripe-processed; historically declined RU cards. | MEDIUM (community reports). | Do not use. |
| **Fly.io** | Stripe-processed. Same risk surface as Vercel; some RU users report success with non-RU-issued cards. | LOW (no official statement). | Test with the actual card you intend to use **before** building production on it. |
| **Railway** | Stripe-processed. Same risk surface. | LOW. | Test before depending on it. |
| **Cloudflare** (Pages, Workers, R2) | Generally still services RU; Pages is free; Workers free tier covers a small directory. | MEDIUM. | Pages for docs is safe. Workers + D1 is a viable directory backend if Fly/Railway both fail. |
| **Yandex Cloud / Selectel / Timeweb Cloud** | Designed for RU customers, accept Mir + RU bank cards. Selectel has English-language interface. | HIGH (their primary market). | **Reliable fallback**, with the caveat that the project's optics become "Russia-hosted." For a directory whose users are global, this matters mildly. |
## Maintenance-Burden Score (army-leave constraint)
| Component | Burden | Notes |
|-----------|--------|-------|
| Python SDK (`http-message-signatures` + `httpx`) | **Low** | Pure library, no network state; sem-ver pin of deps. |
| TypeScript SDK (`web-bot-auth` + native fetch) | **Low** | Same reasoning. |
| FastAPI directory + SQLite on Fly volume | **Low–Med** | Fly volumes need occasional snapshot consideration; SQLite itself is bulletproof. |
| Docs site (Astro Starlight + GitHub Pages) | **Low** | Builds on push; if Astro releases breaking changes, your build fails on next push only — old site keeps serving. Pin `package-lock.json`. |
| PyPI / npm publishing | **Low** | Use PyPI Trusted Publishers (OIDC, no token rotation). For npm, use `--provenance` flag with GitHub Actions OIDC. Both eliminate token expiry. |
| Sentry (optional) | **Med** | Free-tier event quota is the only thing to watch; if exceeded, errors silently drop, but nothing breaks. |
| Cloudflare Verified Bot directory submission | **Low** | One-time submission flow; Cloudflare doesn't churn that. |
| GitHub Issues / community PRs | **High** | This is the burden you cannot eliminate. Plan: pin a `MAINTAINER_AWAY.md` at the top of the repo with expected return date and the message "PRs reviewed asynchronously, no SLA." |
## Stack Patterns by Variant
- Fly.io for FastAPI directory + persistent volume for SQLite
- GitHub Pages for docs
- Standard recommendations above
- Try Railway → if also rejected → Cloudflare Workers + D1 for directory (rewrite directory backend in TypeScript; SDKs unaffected)
- Or Selectel + accept RU-host perception cost
- Cloudflare Workers free tier (100k req/day) + D1 free tier (5 GB, 5M reads/day) → directory entirely on Cloudflare's free tier
- GitHub Pages → docs on GitHub free tier
- This is the most army-leave-proof variant; downside is rewriting directory in TS
- Fly Postgres (managed) — cleanest migration from SQLite
- Or Supabase free tier — only if you want Auth/Realtime later
- Use `tsup` to ship ESM+CJS+types from a single source file (~100 LOC wrapping `web-bot-auth`)
- Don't try to make it isomorphic for browser yet — pure Node target is enough for Browser Use, Stagehand, Skyvern, Playwright
## Version Compatibility
| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| `http-message-signatures==2.0.1` | Python ≥3.10 | 3.10–3.14 supported per PyPI metadata. Pin `python_requires>=3.11` in your SDK to avoid the 3.10 EOL window. |
| `requests-http-signature` (latest) | `requests>=2.x`, `http-message-signatures>=2` | Algorithms enum exposes `ED25519` directly. |
| `cryptography==46.x` | OpenSSL 3.x bundled in wheels | Wheel builds available for all major platforms; no compiler needed for users. |
| `httpx==0.28.x` | `httpcore>=1.0`, `anyio>=4` | FastAPI's TestClient depends on httpx; ensure no version skew with FastAPI's pinned range. |
| `FastAPI 0.118+` | Pydantic v2 (≥2.7), Starlette ≥0.40 | Don't cross-pin — let FastAPI resolve transitives. |
| `web-bot-auth` (Cloudflare) | Node ≥20 (native `crypto.subtle.sign` for Ed25519) | Older Node lacks Ed25519 in WebCrypto. |
| `Astro 5.x` + `Starlight 0.30+` | Node 20+ for build only (not runtime) | Lockfile must be committed; CI build pulls exact deps. |
## Concrete API Sketch (informs roadmap)
# Decorator over httpx client
# One-shot inspector
## Sources
- [http-message-signatures on PyPI (v2.0.1, Jan 2026)](https://pypi.org/project/http-message-signatures/) — verified version, Python 3.10–3.14 support
- [pyauth/http-message-signatures GitHub](https://github.com/pyauth/http-message-signatures) — RFC 9421 compliance, active
- [pyauth/requests-http-signature](https://github.com/pyauth/requests-http-signature) — `algorithms.ED25519` confirmed in source
- [Cloudflare cloudflare/web-bot-auth GitHub](https://github.com/cloudflare/web-bot-auth) — TS + Rust packages, Cloudflare-maintained reference impl
- [npm `web-bot-auth`](https://www.npmjs.com/package/web-bot-auth) — Cloudflare-published TS package
- [Cloudflare Web Bot Auth docs](https://developers.cloudflare.com/bots/reference/bot-verification/web-bot-auth/) — protocol spec, debug endpoint
- [RFC 9421 HTTP Message Signatures](https://datatracker.ietf.org/doc/rfc9421/) — canonical spec
- [draft-meunier-web-bot-auth-architecture-05](https://datatracker.ietf.org/doc/draft-meunier-web-bot-auth-architecture/) — Web Bot Auth IETF draft, references existing impls
- [FastAPI docs](https://fastapi.tiangolo.com/) — version, async patterns, TestClient
- [HTTPX Authentication docs](https://www.python-httpx.org/advanced/authentication/) — custom Auth flow pattern
- [Astro Starlight docs](https://starlight.astro.build/) — current, active
- [Cryptography (PyCA) Ed25519 docs](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/) — keygen + sign API
- [Stytch Web Bot Auth implementation guide](https://stytch.com/blog/how-to-implement-web-bot-auth-signing/) — uses `jose` + Express, JS-only
- [Cloudflare blog: Forget IPs — Web Bot Auth](https://blog.cloudflare.com/web-bot-auth/) — protocol motivation
- [Cloudflare blog: Verified Bots with cryptography](https://blog.cloudflare.com/verified-bots-with-cryptography/) — verifier side
- [OpenBotAuth practical guide](https://openbotauth.com/blog/http-message-signatures-rfc-9421-guide) — RFC 9421 walkthrough
- [Anchor Browser docs on Cloudflare Web Bot Auth](https://docs.anchorbrowser.io/advanced/cloudflare-web-bot-auth) — third-party integration example
- [Fly.io billing docs](https://fly.io/docs/about/billing/) — Stripe-processed
- [Hetzner payment FAQ](https://docs.hetzner.com/accounts-panel/accounts/payment-faq/) — confirms RU-postal-address restriction
- [DigitalOcean payment methods](https://docs.digitalocean.com/support/payment-methods/) — accepted card list, no Mir
- [Railway pricing FAQ](https://docs.railway.com/pricing/faqs) — credit card only
- [Yandex Cloud Managed PostgreSQL](https://yandex.cloud/en/docs/managed-postgresql/) — RU fallback option
- [Selectel](https://selectel.ru/en/) — RU fallback with English UI
- [Material for MkDocs alternatives](https://squidfunk.github.io/mkdocs-material/alternatives/) — author's own list confirming maintenance-mode reality
- [Distr blog: switching from Docusaurus to Starlight](https://distr.sh/blog/distr-docs/) — recent real migration, motivations
- [Astro Starlight + GitHub Pages template](https://github.com/30DaysOf/astro-starlight-ghpages) — working template
- [Astro deploy to GitHub Pages docs](https://docs.astro.build/en/guides/deploy/github/) — official one-step deploy guide
- [Playwright network interception docs](https://playwright.dev/docs/network) — `page.route()` API
- [BrowserStack: intercepting requests with Playwright](https://www.browserstack.com/guide/playwright-intercept-request) — example patterns
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
