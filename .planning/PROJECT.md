# Agent Identity & Policy Toolkit

## What This Is

OSS-первый Python+TypeScript toolkit, который даёт AI-агентам две вещи: (1) **identity** — подписанные HTTP-запросы по IETF Web Bot Auth, чтобы их перестали блокировать Cloudflare/AWS/Akamai как анонимных ботов, и (2) **pre-flight policy** — структурированную картину того, что им разрешено и поддерживается на конкретном сайте (robots.txt, ai.txt, llms.txt, MCP/ACP/AP2 endpoints, rate limits) до первого запроса. Дополняется бесплатным hosted-каталогом `agentpassport.dev`, где любой агент публикует свой identity, а сайты — верифицируют.

Целевые пользователи: разработчики агентных фреймворков и кастомных агентов (Browser Use, Stagehand, Skyvern, Playwright + LLM, OpenAI Agents SDK), которым нужно обходить CAPTCHA-блокировки и не сжигать токены на сайты, которые их явно не пускают.

## Core Value

**AI-агенты получают идентичность и знают свои права на сайте — до того, как сделают первый запрос.** Если ничего другое не работает, эти две вещи (signed identity + pre-flight policy) должны работать в одну строку импорта.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Python SDK для Web Bot Auth signing (Ed25519 keypair, RFC 9421 HTTP Message Signatures, drop-in декоратор для requests/httpx/aiohttp)
- [ ] TypeScript/Node SDK с эквивалентным API (для Browser Use, Stagehand, Playwright экосистемы)
- [ ] Pre-flight policy inspector: одна функция, которая по URL возвращает структурированный объект (robots.txt rules, ai.txt, llms.txt, MCP server discovery via .well-known, ACP/AP2 endpoints, rate-limit hints, Cloudflare bot policy hints)
- [ ] Hosted public directory `agentpassport.dev`: register/lookup/verify публичных agent identities
- [ ] Cloudflare verified-bot directory submission flow (документация + скрипт)
- [ ] Интеграционные примеры в репозитории: Browser Use, Stagehand, Playwright+OpenAI Agents SDK
- [ ] Documentation site (статика, GitHub Pages или Astro): quickstart, API reference, "почему это нужно", FAQ
- [ ] Лендинг с 60-секундным Loom-демо: агент падает на CAPTCHA → ставит SDK → проходит
- [ ] Минимум 3 публичных кейса/демо: один на каждом из (browse Cloudflare-protected site, скрейпинг с уважением к ai.txt, multi-step flow с identity persistence)

### Out of Scope

- **Observability/replay платформа** — Laminar (S24, $3M) и AgentOps уже закрывают это, требует постоянной поддержки, плохо переживёт армейский перерыв
- **Site-side MCP-converter** — chicken-and-egg adoption, требует продаж владельцам сайтов, медленный feedback loop
- **Свой стандарт** — IETF Web Bot Auth и MCP discovery (SEP-1649/1960) уже идут, не дёргаемся
- **Vision-based browser automation** — не наша поляна, дублирует Browser Use/Stagehand
- **Платная monetization в v1** — сначала чистый OSS reach + traction; paid hosted directory tier рассматривается после армии
- **Анти-бот обход / fingerprint-spoofing** — этический и легальный риск, противоречит самой идее «у агента есть identity»
- **Поддержка не-HTTP протоколов (gRPC/WebSocket signing)** — узкая аудитория, добавит complexity без leverage
- **Web UI / dashboard для каталога в v1** — JSON API + CLI достаточно; UI после если будет спрос
- **Site-side SDK для верификации входящих agent requests** — рассматриваем как v2, сначала фокус на agent-side

## Context

**Эпоха агентного веба формируется прямо сейчас:**
- MCP (Anthropic → Linux Foundation) — индустриальный стандарт интеграции тулов, 9 400+ серверов
- WebMCP (Google + Microsoft) — в Chrome 146 за флагом с февраля 2026
- A2A (Google) — ~150 enterprise-внедрений
- IETF Web Bot Auth — активная WG, реализован Cloudflare/AWS Bedrock AgentCore/Akamai/HUMAN/DataDome/Visa/Mastercard
- Agentic AI Foundation (Linux Foundation, дек. 2025) — ~170 членов

**Болевые точки агентов в продакшене (по консенсусу 2025–2026):**
- CAPTCHA / Cloudflare Turnstile — заявленный №1 failure mode (~20% веба блокирует AI по умолчанию)
- 2FA/OAuth re-auth в долгих сессиях
- Сжигание токенов на сайты, которые явно не разрешают AI (нет pre-flight check)
- Trust остаётся нерешённой проблемой; нет единого agent-side SDK для Web Bot Auth

**Релевантные прецеденты по дистрибуции:**
- Browser Use (W25): 91k+ stars за <12 месяцев через OSS-first
- Laminar (S24): дефолт в доках Browser Use → пробил traction за дни
- llms.txt: 844k сайтов внедрили без VC, чисто через distribution

**Текущее состояние конкуренции на нашем клине:**
- Никто не выпустил drop-in agent-side Web Bot Auth SDK для популярных фреймворков
- Никто не объединил identity + pre-flight policy в один пакет
- Cloudflare/AWS реализуют Web Bot Auth со стороны verifier, не provider; туда нужен provider-side tooling
- Klavis/Composio/FastMCP — соседняя поляна (MCP-серверы для апп), не identity/policy

## Constraints

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

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Identity + Policy hybrid (а не чистый identity) | Identity один — узкая ценность; policy один — слабая дистрибуция; вместе — целая история «агент должен иметь identity И знать правила сайта» | — Pending |
| Не выходить на observability/replay клин | Laminar там, требует постоянной итерации, плохо переживёт армейский перерыв | — Pending |
| Не таргетиться на YC S26/F26 | Релокация невозможна, OFAC блокирует инкорпорацию из РФ; сначала строим reputation play | — Pending |
| OSS-first под Apache 2.0, без paywall в v1 | Maximize star velocity и distribution; маркетинг через GitHub + Twitter, не sales | — Pending |
| Python первый, TypeScript параллельно через агентов | Python — нативный стек; TS критичен для покрытия Stagehand/Browser Use, но делегируется | — Pending |
| Hosted directory простая (FastAPI + Postgres) | Должна работать сама в армейский период; никаких сложных микросервисов | — Pending |
| Drop-in API: декоратор + одна функция | Самое заразное в OSS — `@signed` на функцию и `inspect(url)` | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-03 after initialization*
