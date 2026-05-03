# Стратегический меморандум: SaaS + OSS-библиотека «Agent-Friendly Web» для соло-разработчика из Москвы

*Подготовлено 3 мая 2026 года. Источники: дорожная карта MCP и документация Linux Foundation, черновик WebMCP (W3C), NLWeb, эмпирические исследования llms.txt, YC RFS Spring/Summer 2026, новости о финансировании Browser Use / Browserbase / Skyvern / Hyperbrowser / Kernel, IETF-черновики Web Bot Auth, коммерческие протоколы ACP / AP2 / x402 / MPP, правила OFAC и YC по инкорпорации.*

---

## TL;DR

- **Идея «единого стандарта адаптации для агентного веба» — реальна и важна, но сам стандарт уже занят.** На май 2026: MCP (Anthropic → Linux Foundation, 97 млн загрузок SDK в месяц, 9 400+ публичных серверов, поддержка от OpenAI/Google/Microsoft/AWS), WebMCP (Google + Microsoft, W3C Community Group, в Chrome 146 за флагом с февраля 2026), NLWeb (Microsoft, Р.В. Гуха — каждый инстанс NLWeb также является MCP-сервером) и A2A v1.0 (Google + Linux Foundation, ~150 enterprise-внедрений на Cloud Next 2026) уже поглотили практически всё концептуальное пространство, на которое ты собирался зайти. Соло-разработчик не выиграет войну стандартов.
- **Однако два смежных венчурных и при этом solo-buildable клина остаются открытыми**: (1) **слой надёжности / observability / replay для агентных запусков в открытом вебе** (Laminar, YC S24, только что поднял $3M ровно на этом — есть место для более резкого, MCP/WebMCP-aware конкурента), и (2) **гибрид «agent-friendly converter / agent passport»** — однострочная интеграция, которая берёт у сайта существующие активы (OpenAPI, sitemap, accessibility tree) и эмитит MCP-сервер + .well-known/mcp.json + Web Bot Auth-личность + ACP-совместимый продуктовый фид. Speakeasy Gram, FastMCP, Stainless, openapi-mcp-generator и Klavis уже атакуют куски этого, но никто не объединяет агент-сайд (доверие/идентификация) с сайт-сайдом (адаптер), и никто не таргетится на «long-tail сайт среднего размера, который просто хочет быть видимым для агентов». Это — настоящая дыра.
- **Честная математика по YC и соло-фаундерам**: YC прямо запросил эту категорию в Summer 2026 RFS («Software for Agents» и «Dynamic Software Interfaces» — это почти дословно твой тезис). Однако (а) соло-фаундеры с пропиской в РФ упираются в OFAC: с июня 2022 американским registered agent service запрещено регистрировать компании для российских резидентов/граждан, то есть инкорпорация и участие в YC требуют либо релокации, либо ко-фаундера в другой юрисдикции; (б) YC-планка для соло-фаундеров заметно выше (~10% батча); (в) «обёртка над MCP в виде SDK» рискует остаться отличным GitHub-проектом, но не венчурно-масштабной компанией. **Итоговая рекомендация: строй клин (1) — инфраструктуру надёжности и replay для агентных запусков, спозиционированную под эпоху WebMCP/MCP — как OSS-first проект, параллельно начинай личный релокационный трек (Ереван / Тбилиси / Белград / Лимассол), и таргетируйся на батч F26 (осень 2026) или W27, а не дёргайся на дедлайн S26 4 мая 2026.**

---

## Ключевые находки

### 1. Ландшафт стандартов агентного веба больше не «открытый» — он сошёлся

| Стандарт | Кто стоит за ним | Статус (май 2026) | Практическая роль | Честная критика |
|---|---|---|---|---|
| **MCP** | Anthropic → Linux Foundation (Agentic AI Foundation, дек. 2025) | De facto индустриальный стандарт. 97M загрузок SDK в месяц (март 2026), 9 400+ серверов в публичном реестре (апр. 2026, +18% MoM), 78% корпоративных AI-команд имеют ≥1 MCP-агента в проде. Нативно в Claude, ChatGPT (Apps SDK + Connectors), Gemini API, Vertex AI, Cursor, Windsurf, Zed, JetBrains, Vercel AI SDK, OpenAI Agents SDK. | Слой интеграции инструментов/данных между агентом и внешними системами. JSON-RPC + Streamable HTTP. | Тяжёлая токенная цена (DB-сервер на 106 инструментов жрал 54 600 токенов только на инициализацию; исследование MCPGauge нашло раздувание контекста до 236x); auth по-прежнему сервер-за-сервером; «MCP is dead, long live the CLI» висел на топе HN; Гарри Тан публично критиковал auth/cost весной 2026. Сообщество отвечает через SEP-1649/1960 (well-known discovery), MCP Apps (UI-расширения) и Code Mode-паттерны (Cloudflare заявил 98% экономии токенов). |
| **WebMCP** | Microsoft + Google, W3C Web Machine Learning Community Group | Draft Community Group Report от 10 фев. 2026; в Chrome 146 Canary за флагом `chrome://flags/#enable-webmcp-testing`, выкатка в stable — март 2026. `navigator.modelContext.registerTool(...)` плюс декларативный `<form toolname="...">`. | Браузерный двойник MCP. Сайты выставляют JS-вызываемые инструменты, и in-browser-агенты (Atlas, Comet, Gemini) дёргают их вместо клика по пикселям. Заявленное снижение compute overhead ~67% против скриншотинга. | Всё ещё draft; нет позиций Firefox/Safari; нет discovery-истории (надо приземлиться на страницу); single-tab scope; спека двигается (`provideContext`/`clearContext` удалили в марте 2026). Это **ровно** твой тезис — и Google + Microsoft уже выпускают это в доминирующем браузере. |
| **NLWeb** | Microsoft (Р.В. Гуха — RSS, RDF, Schema.org) | Анонс Build 2025; растущая reference-implementation usage (TripAdvisor, Cloudflare AI Search ships NLWeb worker template, BBC, O'Reilly и т.д.). В мае 2025 был CVE-class флоу в reference impl. | Natural-language `ask`-эндпойнт поверх существующих Schema.org/RSS-данных сайта. Каждый инстанс NLWeb также является MCP-сервером, поэтому автоматически мостится в MCP-экосистему. | Узкий примитив (один метод против произвольных тулов); ценен только для контентных сайтов; зависит от внедрения Schema.org. Microsoft позиционирует это как «HTML агентного веба» — пока амбиция, не реальность. |
| **llms.txt** | Джереми Ховард (Answer.AI), сент. 2024 | ~844 тыс. сайтов к окт. 2025; исследование SE Ranking на 300 тыс. доменов (2025) **не нашло измеримого эффекта на цитирование AI**; Джон Мюллер из Google публично заявил «никакая AI-система сейчас не использует llms.txt»; OpenAI/Anthropic/Google не давали никаких обязательств. | Plain markdown-карта сайта, указывающая AI-краулерам на ценные страницы. | В основном культовое SEO. 30 минут на публикацию, но строить стратегию вокруг этого нельзя. |
| **agents.json** | Wildcard AI (открытая спека, расширение OpenAPI) | Живёт по `/.well-known/agents.json`; mainstream-внедрения не достиг — концептуально перекрыт MCP + WebMCP. | Stateless, OpenAPI-типизированные цепочки действий для агентов. | В основном история; фаундеры цитируют чаще, чем агенты используют. |
| **A2A (Agent2Agent)** | Google + ~50 партнёров → Linux Foundation, Apache 2.0 | Спека v0.3; Google заявил ~150 enterprise-внедрений в проде на Cloud Next 2026 (апр. 2026). Salesforce, ServiceNow, S&P, Box, Workday, UiPath, Atlassian, Cohere, MongoDB, PayPal, SAP — все шипают. | Inter-agent коммуникация. Сидит **над** MCP/WebMCP — агенты говорят через A2A, но дёргают тулы через MCP/WebMCP. Использует «Agent Cards» по `/.well-known/agent.json`. | Сейчас доминируют enterprise-интеграторы и SI-партнёры; не место для соло-дева. |
| **Web Bot Auth** | Черновик IETF (HTTP Message Signatures), ведут Cloudflare / Mark Nottingham | Активная IETF-рабочая группа (BoF в Бангкоке); уже реализовано Cloudflare, AWS Bedrock AgentCore Browser (preview), Akamai, HUMAN, DataDome, embed-ы Visa/Mastercard/Amex для agentic commerce. Google шипит `Google-Agent` с identity `https://agent.bot.goog`. | «Agent passport» — Ed25519-подписанные HTTP-запросы, чтобы сайты могли whitelist-ить легитимных AI-агентов и пропускать CAPTCHA. | Ценность раскроется только когда станет повсеместно требуемым; chicken-and-egg adoption. **Реальная solo-возможность — см. ниже.** |
| **Schema.org / ARIA / Accessibility Tree** | W3C/WHATWG | Зрелое. OpenAI Atlas, Anthropic Computer Use, Microsoft Playwright MCP, paper Perplexity Comet BrowseSafe — все подтверждают, что гибридные агенты предпочитают accessibility tree (~4k токенов) скриншотам (~50k токенов). | Существующий semantic web — де-факто слой восприятия для агентов, когда больше ничего нет. | Уже построено; нет дыры под новый стандарт. |
| **Agentic Commerce stack** | OpenAI+Stripe (ACP), Google+Shopify (UCP/AP2), Coinbase+Cloudflare (x402), Stripe+Tempo (MPP) | Все запущены между сент. 2025 и апр. 2026. ACP живой в ChatGPT Instant Checkout; AP2 — 60+ партнёров; x402 в проде у Cloudflare/Stripe; MPP запущен 18 марта 2026. | Слой платежей/чекаута для agent-to-business и agent-to-agent. | Жёстко удерживается гигантами; не для соло-дева. |
| **Open Agent Spec (Oracle), AgentSpec, AG-UI (CopilotKit), A2UI (Google)** | Разные | Нишевые тулинги/манифесты. AG-UI имеет тягу под agent↔frontend event streaming, в марте 2026 интегрирован с Oracle Agent Spec. | Internal-DSL территория — не публичный веб-адаптер. | Ни у одного нет гравитации MCP. |

**Browser-automation / DOM perception фреймворки** (релевантно «где агенты сегодня падают»):

| Инструмент | Финансирование / статус | Подход | Заметка |
|---|---|---|---|
| **Browser Use** (YC W25) | $17M seed (март 2025, лид Felicis, ангел Paul Graham). 91k+ GitHub stars, самый быстро растущий OSS-агентный проект 2025. | Python; конвертит страницу в структурированный текст (DOM-first), 89.1% на WebVoyager. | Open-core; их thesis буквально — «следующий миллиард пользователей — агенты, и веб не построен под них». То есть **дословно твой тезис**, и они уже на 12 месяцев и $17M впереди. |
| **Browserbase** | $40M Series B июнь 2025 при $300M, всего $67.5M. Владеет Stagehand (22k stars) + Director (no-code) + Cloudflare/CDP-интеграциями. Cash App, Rye, 1 000+ клиентов. | Облачная headless-browser инфра («AWS для headless browsers»). | Слой инфры, на котором живут все, кто выше. |
| **Stagehand** | OSS Browserbase, 22k stars. | TypeScript-on-Playwright с AI-примитивами `act()`/`extract()`/`observe()` + автокеширование. | DX-лидерский паттерн; многие копируют. |
| **Skyvern** | Меньше; сильный vision-подход. | Computer-vision + form-filling специалист; 85.85% WebVoyager, лидирует на «WRITE»-сабсете. | Вертикальный пивот в страхование/permit-формы. |
| **Kernel** (YC S25, Accel) | YC + Accel. | Unikernel-based browser infra, sub-150ms cold starts, residential proxies, SOC2/HIPAA. | Прямой инфра-конкурент Browserbase. |
| **Hyperbrowser** (YC) | YC. | Stealth-first browser-as-a-service; HyperAgent framework. | Stealth/anti-bot — это и есть продукт. |
| **Multi-On / Skyvern / Browseract** | Разные мелкие | Микс vision + DOM. | Long-tail commodity. |
| **Anthropic Computer Use / OpenAI CUA / Operator** | Натив frontier-лаб | Чистое pixel/screen vision. | DOM-driven стеки бьют их на 12–17 пунктов надёжности и в 4–8 раз по стоимости там, где DOM есть; vision — fallback. |
| **Cloudflare Browser Run** (ребрендинг Browser Rendering, март 2026) | Cloudflare | Добавил Live View, Human-in-the-Loop, Session Recordings, raw CDP-эндпойнт. | Cloudflare гонит за владение слоем «commodity infra для агентов». |

**Production-консенсус (апрель 2026):** DOM-driven primary + vision fallback; accessibility tree — самая дешёвая надёжная поверхность восприятия; ~85% success rate на WebVoyager — это SOTA, но **продакшн** success на сайтах под Cloudflare сильно ниже, потому что ~20% веба блокируют AI по умолчанию (данные Cloudflare: некоторые AI-краулеры шлют 71 000 запросов на один реферальный клик). CAPTCHA — заявленный №1 failure mode. Аутентификация, динамический JS-state, multi-step flows, платежи и анти-бот системы — основной массив падений в середине задачи.

---

### 2. Где реальный gap, а где — нет

**НЕ в предложении нового стандарта.** Standards-setting capacity уже занят: Anthropic (MCP), Microsoft+Google (WebMCP), Google (A2A, AP2), Microsoft (NLWeb), OpenAI+Stripe (ACP), IETF (Web Bot Auth, MCP discovery URI). Agentic AI Foundation (Linux Foundation, основан в дек. 2025 Anthropic + OpenAI + Block + AWS + Google + Microsoft + Cloudflare + Bloomberg, ~170 членов за <4 месяца) — это площадка, где сейчас и происходит стандартизация. У соло-разработчика из Москвы нет пути выиграть там.

**ЕСТЬ — в уродливой средней прослойке между стандартами и реальностью.** Конкретно:

1. **Reliability/observability агентных запусков на открытом вебе.** Laminar (YC S24, Robert Kim & Dinmukhamed Mailibay, оба родом из Казахстана — релевантный прецедент для founder из РФ) поднял $3M seed в марте 2026 от Atlantic.vc + YC + Бен Зигельман (создатель OpenTelemetry) + Ant Wilson (CTO Supabase) ровно на этом тезисе: существующие observability-инструменты строились под одиночные LLM-вызовы и не вытягивают агентов, которые крутятся часами, генерят тысячи спанов и требуют браузерного session replay. Laminar теперь дефолт в доках Browser Use и интегрирован с OpenHands. Replay.io шипает MCP-сервер для time-travel debugging. Browserbase, Cloudflare Browser Run, AWS AgentCore, AgentOps — все построили session replay. **То есть клин реальный, но уже оспариваемый на инфра-слое.** Соло-игроку нужна вертикаль или угол (например, MCP-tool-call replay конкретно, или классификация root-cause failure агентов, или free OSS-first wedge, который инкумбенты не смогут повторить, не подорвав свой бизнес).

2. **«Agent passport» / Web Bot Auth identity SDK.** Web Bot Auth — реальная IETF-группа с chicken-and-egg-adoption. AWS шипает в AgentCore (preview). У Cloudflare задокументированная интеграция. DataDome поддерживает. Но **никто** не выпустил трёхстрочный drop-in SDK, который любой агентный фреймворк (Browser Use, Stagehand, Skyvern, кастомный Playwright) импортит и сразу подписывает запросы плюс публикует free hosted-директорию. Это honestly buildable соло, есть чёткий канал дистрибуции в экосистему агентных фреймворков (PR в Browser Use → 91k stars распространяют тебя), и едет на волне стандарта, который тебе не надо выигрывать — только реализовать первым.

3. **Автогенерация MCP-серверов из существующих ассетов сайта — для long tail.** FastMCP (`from_openapi`), Stainless, Speakeasy Gram, openapi-mcp-generator, awslabs.openapi-mcp-server — все уже делают OpenAPI → MCP. Klavis (YC) делает hosted MCP servers для топовых апп. **Но никто не закрыл «не-API» путь**: взять сайт, у которого только sitemap + Schema.org + accessibility tree, и эмитнуть (а) MCP-сервер, обёртывающий его read-эндпойнты, (б) `.well-known/mcp.json` (по SEP-1649/1960), (в) `agents.json` или AP2 Agent Card, (г) hosted-эндпойнт. Блог Neon и критики «1:1 OpenAPI→MCP» прямо говорят: **автогенерированные 1:1 MCP-обёртки — это плохо**, но курированная, agent-workflow-центричная обёртка (например, «search → product detail → cart» как один tool, не три) — ровно то, что показал MCP-сервер GitHub (600+ эндпойнтов сжали до ~30 полезных тулов). Это правильный паттерн.

4. **Вертикальные «agent-ready» вертикали.** YC S26 RFS прямо называет «Dynamic Software Interfaces» и «Software for Agents». Но горизонтально атаковать это против Anthropic/Google/Microsoft — мёртво. Вертикально (e-commerce-only agent storefronts, gov-form agent layer, банковские дашборды для агентов) — место есть.

**Консенсус практиков из HN/X/agent-framework кругов (2025–2026):**
- «MCP — самая хуже задокументированная технология, с которой я работал» — топовый коммент HN.
- «MCP и function calling — не конкуренты. Function calling — это API модели; MCP — слой интеграции выше» — вырисовывающийся консенсус.
- «MCP над stdio — туда копятся все проблемы; remote streamable HTTP + .well-known — туда оно идёт» — мейнтейнеры дорожной карты MCP.
- «Чисто AI-автоматизация слишком медленная и дорогая; чисто детерминированная — слишком ломкая. Выигрывает гибрид» — повторяется в доках Stagehand/Browser Use.
- «Trust остаётся нерешённой проблемой. У WebMCP нет trust-модели. У MCP есть аутентификация, но нет feed-level trust» — WellKnownMCP project, фев. 2026.
- Самые часто называемые pain points практиков: **CAPTCHA / Cloudflare Turnstile** (один тестер сообщил, что даже живые люди фейлятся, потому что **браузерное окружение** флагается до того, как появляется challenge), **2FA/OAuth re-auth в долгих сессиях**, **dynamic-form state machines**, **cross-tab/cross-domain auth carryover**, и **отладка «почему агент упал на шаге 47»**.

---

### 3. Поклинговый разбор для соло-Python-сильного дева

| # | Клин | Кто уже это делает | Сложность для соло (1–10) | Жизнеспособность бизнес-модели | YC fit | Вердикт |
|---|---|---|---|---|---|---|
| **(а)** | **OSS SDK, оборачивающий MCP + WebMCP + accessibility tree + llms.txt в один лёгкий интерфейс для разработчиков агентов.** | mcp-agent (lastmile-ai, OSS), Composio (1 000+ тулов, MCP-native), Arcade.dev, Klavis, Pipedream MCP (Workday-acquired нояб. 2025), Nango, Scalekit, Membrane. | 4 — Python SDK поверх существующих протоколов, в пределах solo-руки. | Слабо. Это тулинг-проект, не компания. Composio/Arcade/Klavis на 18–24 месяца впереди с платными тарифами и клиентами. Free SDK → cloud SaaS pivot имеет жёсткий потолок. | Низкий. YC уже профинансировал нескольких в этом ровно лейне (Klavis). | **Пропустить как primary play. Сделать тонкую версию как surface-канал дистрибуции для (б) или (в).** |
| **(б)** | **«Сделай мой сайт agent-friendly» конвертер для владельцев сайтов.** Авто-эмит MCP-сервер + `.well-known/mcp.json` + Web Bot Auth verification + agent-friendly ARIA-улучшения. | FastMCP, Stainless, Speakeasy Gram (managed), openapi-mcp-generator, AWS openapi-mcp-server, Cloudflare AI Search/NLWeb worker template, Stripe Agentic Commerce Suite for retail. | 6 — управляемо, но дистрибуция к не-разработчикам владельцам сайтов — это и есть настоящая работа, а ты сам пишешь, что sales/distribution слабые. | Средне. Владельцы сайтов пока не чувствуют боль настолько, чтобы платить (аналогия с llms.txt: 844k сайтов внедрили, ноль доказанного ROI). Покупателю нужен чёткий сигнал «агенты приносят мне выручку» — этот сигнал начинает приходить (ChatGPT Instant Checkout через ACP), но в основном к крупным ритейлерам, которых Stripe ловит напрямую. | Средне-низкий. YC финансировал NLWeb-смежных (Klavis), но «site-side» плеи медленнее растут. | **Реалистично, но тайминг — 2027. Запарковать как future pivot.** |
| **(в)** | **Слой надёжности / observability / replay для агентных запусков.** Диагностировать, логировать, реплеить, root-cause: почему агент X упал в середине задачи на сайте Y. | **Laminar (YC S24, $3M seed март 2026)**, Replay.io (MCP time-travel debugger), AgentOps, Langfuse, Helicone, Browserbase Observability, Cloudflare Browser Run Live View, AWS AgentCore session replay, Datadog Synthetic Monitoring (расширяет покрытие на агентов). | 6 — Python instrumentation, OpenTelemetry, Redis/Supabase под хранение спанов, Playwright/CDP-интеграция, replay UI. Всё в твоём стеке. | **Сильно при дифференциации.** Категория достаточно горячая, чтобы Laminar получил финансирование явно, но достаточно маленькая, чтобы несколько игроков сосуществовали. OSS-дистрибуция в Browser Use / Stagehand / OpenHands — доказанный flywheel (Laminar буквально это и сделал). | **Высокий** — прямое попадание в YC «Software for Agents» RFS, и YC только что профинансировал по сути идентичную компанию в S24. | **Топ-рекомендация. Смотри план исполнения ниже.** |
| **(г)** | **Anti-detection / agent-passport сервис** (Web Bot Auth implementation, signed-request SDK, agent verification directory). | Cloudflare (ships verification), AWS AgentCore (signs), DataDome/Akamai/HUMAN (verify), Stytch (auth для агентов), WorkOS (auth для агентов), IETF webbotauth WG. | 5 — Ed25519-ключи, HTTP message signatures (RFC 9421), маленькая директория, SDK на 3 языках. Honestly соло-buildable за 4–6 недель. | Средне. Two-sided market (агенты + сайты), что сложно. Но если фокусишься сначала на агент-сайде («импортируй это и больше никогда не решай CAPTCHA на Cloudflare-verified сайтах»), дистрибуция односторонняя. Монетизация через hosted directory + enterprise tier + verification-as-a-service. | Средне-высокий — попадает в «Software for Agents» + agentic commerce trust narrative. | **Сильная вторая опция. Можно совместить с (в).** |
| **(д)** | **Предложить новый стандарт.** | Уже сделано всеми, кого стоит перечислить. | 3 (написать спеку), 9 (получить adoption). | Незначительно без дистрибуции. | Никакого. | **Не делай.** |
| **(е)** *(emergent)* | **MCP-failure-aware test harness для агентных платформ.** Штука, которая обходит сайт, пробует агентные задачи, оценивает надёжность и эмитит структурированный отчёт («твой сайт фейлится на этих flow для этих агентов»). | Skyvern evals/eval.skyvern.com, Browser Use WebVoyager harness, AgentBench академические бенчмарки. | 5. | Средне. Продаёт **разработчикам агентных платформ**, не владельцам сайтов — точное попадание в твой заявленный target customer. | Средне. | **Solid third option; гибрид с (в).** |

---

### 4. YC fit и прецеденты

**Заявленный тезис YC (Spring + Summer 2026 RFS, авторы — Гарри Тан, Диана Ху, Джаред Фридман, Пит Куумен):**

> *«Следующий триллион пользователей в интернете — это не люди, это AI-агенты. Нужны API, MCP, CLI, machine-readable документация, identity, permissions, payments и agent-native software.»* — *Software for Agents*, S26 RFS

> *«AI делает пользователей их собственными forward-deployed engineers. Софт может стать набором примитивов, которые пользователи и агенты кастомизируют под свои workflow.»* — *Dynamic Software Interfaces*, S26 RFS

Твой тезис — **буквально одна из категорий YC 2026 года**. Это редкая валидация, но также значит, что конкуренция дикая — каждый, кто прочитал этот RFS, сейчас подаётся с похожим питчем.

**YC-финансированные сравнимые (W24 → W26, все релевантны):**

| Компания | Батч | Питч | Финансирование |
|---|---|---|---|
| Browser Use | W25 | «Open-source web agents.» DOM-first browser automation. | $17M seed на нераскрытой оценке, март 2025 (Felicis lead, Paul Graham). 91k stars. |
| Browserbase | (pre-YC, но YC-смежный нетворк) | Headless-browser infra для агентов. | $67.5M total, $40M Series B при $300M (июнь 2025). |
| Klavis AI | YC | Hosted MCP servers + live training environments. | Активный. |
| Hyperbrowser | YC | Browser infra for AI agents. | Активный. |
| Kernel | S25 | Unikernel-based быстрый-cold-start browser infra, нативно ко всем browser/computer-use фреймворкам, SOC2/HIPAA. | Backed by Accel + YC. |
| Abundant | W25 | API для AI agent teleoperation (human takeover, когда агент фейлится). | Активный. |
| Asteroid | W25 | Runtime supervision / guardrails для AI-агентов. | Активный. |
| Laminar | S24 | Agent observability + browser session replay. | $3M seed март 2026, дефолт в Browser Use. |
| Lucidic AI | W25 | «Weights & Biases для AI-агентов.» | Активный. |
| Wild Card AI | (около W24/S24) | agents.json + Bridge SDK. | Сейчас менее заметен. |

**Наблюдение: YC профинансировал ≥6 компаний в этом конкретном клине за последние 4 батча.** Это значит, что YC **не** перенасыщен (продолжают финансировать новых), но это значит, что **дженерик-питч «MCP wrapper SDK» не выделит тебя**. Нужен острый угол — у Laminar он был «нас по дефолту используют доки Browser Use»; у Kernel — «sub-150ms cold start через unikernels»; у Abundant — «Waymo-style human teleoperation для агентов». Твой должен быть одним конкретным глаголом, который агентные платформы не могут легко собрать сами.

**Нет прямого RFS, запрашивающего «единый стандарт адаптации для агентного веба»**, но «Software for Agents» + «Dynamic Software Interfaces» это покрывают. И нет RFS, который бы прямо запрещал — каждый пункт RFS это подсказка, не забор.

**Типичная traction для YC-fundable infra-for-agents соло-фаундера, май 2026:**
- Для idea-stage заявки: рабочий OSS-прототип с **1–3 тыс GitHub stars** в первые 60 дней ИЛИ **5–10 named pilot users из YC-финансированных агентных компаний** (можешь холодно писать пользователям Browser Use, Stagehand, Skyvern в YC alumni Slack — этот сигнал золотой), ИЛИ чёткая техническая дифференциация (реальная победа в бенчмарке, например «мы добавляем 14 п.п. к WebVoyager success rate на сайтах под Cloudflare»).
- 40% акцептованных YC компаний — pre-revenue, но ВСЕ имеют evidence проблемы, в идеале артикулированной людьми, которые бы купили.

**Соло-фаундер математика на YC:** ~10% последних батчей; планка выше; нужно компенсировать «bus factor» исключительной скоростью шиппинга и проблемой, которую ты понимаешь уникально. Казахстанский бэкграунд фаундеров Laminar — релевантный прецедент, но они подавались как два человека через стандартные YC-каналы.

---

### 5. Реальность Москвы (этот раздел не пропускай)

Это самое большое ограничение, и в твоём разборе оно недооценено.

- **OFAC SDN List, 23 фев. 2024**: НСПК (Мир/Russian National Card Payment System) под санкциями. Граждане/резиденты РФ глубоко ограничены в доступе к финансовой инфре США с 2022.
- **OFAC Determination, 8 мая 2022 (вступила в силу 7 июня 2022)**: запрещает американским registered agents и сервисам инкорпорации формировать юр.лица или предоставлять registered-agent service «любому лицу, находящемуся в Российской Федерации». Harvard Business Services, Stripe Atlas, Clerky и большинство крупных US-инкорпораторов публично перестали принимать клиентов с гражданством/резиденством РФ. **Это значит: ты сегодня, из Москвы, имея только российский ID и российский адрес, не откроешь Delaware C-Corp через нормальные каналы.**
- **Стандартные условия YC**: YC инвестирует только в компании, инкорпорированные в США, Канаде (вернули в 2025), Каймановых о-вах или Сингапуре. Помогут флипнуть foreign entity, но сам флип идёт через US-юристов и US registered agents — упирается в ту же OFAC-стену.
- **Stripe/Mercury/Brex банкинг**: закрыт для KYC только-РФ.
- **Штраф GVA Capital (июль 2025)**: $216M OFAC penalty против SV-VC за facilitation доступа российского гражданина к финансовой системе США — это warning shot для VC по работе с principals из РФ. Большинство US VC сейчас отказывают РФ-domiciled фаундерам из risk hygiene, даже если индивидуально комплаенс ок.
- **In-batch travel**: с YC W22 batch in-person в Сан-Франциско. Российскому паспорту нужна B-1/B-2 (rejection rate сейчас крайне высокий) или резиденция третьей страны. Белград, Ереван, Тбилиси, Лимассол, Алматы — практические релоцентры для ex-РФ tech-фаундеров.

**Практические пути (по нарастанию серьёзности):**

1. **Релоцируйся физически до подачи.** Возьми больничный → Ереван (визфри, доступ к банкам, established russian-tech диаспора, 4 часа лёта), Тбилиси или Белград. Получи residence card. **Тогда** инкорпорируйся через Stripe Atlas / Clerky / Firstbase с новым адресом. Многие YC-alumni из РФ прошли через Армению и Кипр конкретно. Аркадий Волож формально отказался от российского гражданства в феврале 2026 — крайний пример, но более широкий паттерн реальный.
2. **Ко-фаундер в несанкционной юрисдикции.** Решает и legal/banking-проблему, и YC solo-discount. Правильный ко-фаундер для агент-инфра плея — TypeScript/frontend-сильный билдер (ты Python-сильный) — ищи в OSS-комьюнити агентов (Browser Use Discord, MCP working groups, Composio Discord).
3. **Cayman или Singapore parent без US-присутствия.** Cayman honestly permissive, но дорогой ($5–10k setup, ongoing accounting). Singapore чище, но требует local director. Оба достижимы из РФ, но KYC для открытия Cayman bank account как гражданину РФ — жесть.
4. **Остаться в Москве и подаваться всё равно.** Честная оценка: сигнал YC interview будет резко негативным в момент, когда «где живёшь» отвечается «Москва». Не делай так.

**Дистрибуция из РФ (отдельно от инкорпорации):** В основном ок. GitHub, X, Hacker News, Discord, Telegram — всё работает. Stripe payouts — нет. Используй Lemon Squeezy / Paddle для SaaS billing, как только будет non-РФ entity; до этого держи проект чистым OSS и не зарабатывай.

---

### 6. Честный риск-регистр

| Риск | Вероятность | Серьёзность | Митигация |
|---|---|---|---|
| **Стандарты выигрывают большие игроки (Anthropic — MCP, Google — A2A/AP2/UCP, OpenAI — ACP, Microsoft — NLWeb/WebMCP).** «Новый стандарт» соло-дева мёртв на старте. | ~95% | Полная | Не предлагай стандарт. Имплементируй существующие лучше всех. |
| **Vision-based агенты (Operator/CUA/Computer Use) делают структурированные agent-слои obsolete.** | Низкая (~15%) | Высокая | Эмпирически неверно на май 2026: DOM-driven бьёт vision-driven на 12–17 пунктов надёжности и в 4–8 раз по стоимости. Даже Atlas/Comet используют accessibility tree primary + vision fallback. Вероятность медленно растёт (vision модели улучшаются), но не быстро для 24-месячного горизонта. |
| **Клин коллапсирует в MCP.** Чистый «MCP-helper SDK» — отличный GitHub-проект, не венчур. | ~70% | Высокая | Поэтому рекомендация — **observability + replay + Web Bot Auth**, а не «обёртка вокруг MCP». Observability сидит **смежно** с MCP, не поверх, и $3M Laminar показывает, что VC оценивает это как категорию. |
| **Open source ≠ выручка.** | ~80% by default | Severe | Playbook Browser Use / Browserbase / Laminar / Composio — open-core: free OSS как дистрибуция + платный hosted/enterprise/observability. Планируй с недели 1, но не paywall-ь OSS — это убьёт star velocity. |
| **OFAC / банкинг / YC инкорпорация.** | ~95% при оставании в Москве | Полная | Релоцируйся. Точка. |
| **Solo-founder ceiling в YC.** | ~75% на первой подаче | Высокая | Шипай заметную OSS-traction (>1k stars, named users) для компенсации. Не подавайся на S26 (дедлайн 4 мая 2026, завтра) — подавайся на F26/W27 с 4–6 месяцами evidence. |
| **Telegram bots / Supabase / Redis стек ок, но русскоязычная документация — это tell** в YC-аппе. | ~40% | Средняя | Пиши всё (README, docs, blog posts, X, demo videos) на native-quality English с дня 1. Используй Claude/GPT-5 для polish, не fake-ай. |
| **Burnout на больничном.** 8 ч/день несколько недель потом 2–4 ч/день — реалистично, но оптимистично; agent-infra OSS требует агрессивной итерации, чтобы удержать stars. | ~50% | Средняя | Бери клин узкий настолько, чтобы зашипить реальное демо в первые 2 недели. |

---

## Финальная рекомендация

### Чистая оценка

| Параметр | Оценка (1–10) | Обоснование |
|---|---|---|
| **Сила идеи (перспективность)** | **6/10** | Высокоуровневый тезис верный («агенты — следующий миллиард пользователей; веб не готов») и явно поддержан YC S26 RFS — но headline-формулировка («единый стандарт адаптации») опаздывает на 12 месяцев. Стандарты есть; мета-игра теперь — качество имплементации. |
| **Техническая сложность для соло** | **7/10** доступно / **3/10** difficulty | Стек (Python, Supabase, Redis, microservices, Playwright/automation) — ровно тот, что нужно. Сложнее не код, а шипинг в категории, где Browser Use, Browserbase, Composio, Klavis, Laminar, Kernel и Hyperbrowser уже существуют и нормально профинансированы. |
| **YC fit** | **6/10** для широкого тезиса; **8/10** для конкретного рекомендованного клина | YC прямо RFS-нул эту категорию. Solo + РФ — heavy discount. |
| **Реалистичный 12-месячный upside** | $0–$3M seed при отличной экзекуции и релокации; OSS-only с 5–15k GitHub stars, 50–200 production users, без финансирования — если релокации не будет. |

### Топ 1–2 клина для атаки

**Primary клин — «слой надёжности + replay для агентов в открытом вебе».**
Собери OSS Python SDK + маленький cloud-дашборд, который:
1. Инструментирует любой агентный run (Browser Use, Stagehand, Playwright + Claude, OpenAI Agents SDK, кастомные MCP-клиенты) одним декоратором.
2. Захватывает: каждый MCP tool call, каждый DOM-mutation, каждую page navigation, каждую LLM-итерацию, каждый failure (timeout, CAPTCHA, 4xx/5xx, hallucination flag).
3. Даёт time-travel replay любого упавшего шага в браузере.
4. Авто-классифицирует failures: «заблокировано Cloudflare Turnstile», «требуется OAuth re-auth», «изменилась схема формы», «MCP tool вернул пустоту», «контекст превысил N токенов».
5. Free OSS local mode; hosted cloud за $X/мес за retention + team features + LLM-powered root-cause classification.

Дифференциация против Laminar — выбери ровно одно из:
- **MCP-tool-call native** (Laminar — browser-and-LLM-call native; MCP tool calls внутри run — растущая поверхность падений, и Laminar их трактует как black-box LLM-события).
- **Failure-mode classification engine** на публичном датасете 10k размеченных агентных падений, который ты сам соберёшь из публичных runs / WebVoyager / своей беты.
- **Open eval harness для агентных платформ** (гибрид с (е)) — продаёт «мы агентная платформа, нам нужно знать reliability across 1000 рандомных Cloudflare-protected сайтов».

**Secondary клин для надстройки к месяцу 3 — «agent passport SDK».**
Трёхстрочный drop-in для любого агентного фреймворка, который подписывает HTTP-запросы по Web Bot Auth + менеджит Ed25519 keypair + публикует `.well-known/ai-agent.json` + интегрируется с verified-bot directory Cloudflare. Free SDK, paid hosted directory + verification API. Самый дешёвый дополнительный дифференциатор и естественно ложится рядом с observability (твой SDK уже оборачивает каждый исходящий HTTP).

**НЕ преследуй:** клины (а), (д) или «agent-friendly converter для site owners» (б) как первый ход. Они медленнее монетизируются и больше оспариваются.

### Конкретный 8-недельный план

**Допущения:** ты в Москве, на больничном, ~8 ч/день первые 4 недели, потом ~2–4 ч/день. Native-quality Python; слабый английский копирайт и sales. Не можешь оплатить US инкорпорацию сегодня.

**Неделя 1 (валидация, скелет)**
- *Дни 1–2:* Прочитать end-to-end: спека MCP 2026 + roadmap, WebMCP draft, Web Bot Auth IETF draft, репо Laminar (lmnr-ai/lmnr), репо AgentOps, доки Browser Use observability, MCP-сервер Replay.io. Найти, чего конкретно **не хватает**.
- *Дни 3–5:* Сесть на one-sentence клин («`pip install agentwatch` — root-cause classification для упавших агентных runs, MCP-native, 3-line instrumentation»). Купить домен. Поднять лендинг (Carrd или Astro) с 60-секундным Loom-демо инструментированного Browser Use run, падающего на Cloudflare-protected сайте, и твой инструмент показывает «blocked by Cloudflare Turnstile, рекомендую Web Bot Auth».
- *Дни 6–7:* Запостить лендинг в r/LocalLLaMA, Browser Use Discord, MCP CWG Discord, AAIF Slack. Цель: 50 email-подписок + 10 разговоров с пользователями агентных фреймворков. **Закрывай проект здесь, если не получишь 50 подписок за неделю** — это самый дешёвый kill-сигнал и экономит 7 недель.

**Неделя 2 (MVP build)**
- Собрать Python SDK: instrumented decorator + OpenTelemetry export + локальный SQLite под traces + крошечный FastAPI dashboard. Стек попадает в твои сильные стороны: Python + FastAPI + Redis (live span streaming) + Supabase (cloud auth/storage когда флипнёшь cloud-сторону).
- Интегрироваться явно с: Browser Use (highest-leverage; Laminar там уже, но сделай свой проще в установке), Stagehand (TypeScript port — оплати контрактору или используй Codex CLI), и OpenAI Agents SDK.
- Open-source на GitHub с polished README. Apache 2.0.

**Неделя 3 (дистрибуция и traction)**
- Submit PR в `examples/` директорию Browser Use, добавляющий твой декоратор. То же в Stagehand. То же в mcp-agent.
- Технический пост: *«Мы инструментировали 1 000 публичных агентных runs. Вот ровно почему они падают.»* Питч на Hacker News во вторник утром PT. Это твой самый важный одиночный шипинг-момент за 8 недель.
- Цель: 500 GitHub stars к концу недели.

**Неделя 4 (early users + план релокации)**
- Холодно написать 30 фаундерам YC W25/S25/W26, строящим что-то агентное (Klavis, Lucidic, Asteroid, Abundant, пользователям Browser Use и т.д.), предлагая free white-glove онбординг. Цель: 5 named users; 10 logos на лендинг.
- *Параллельно:* брать билет в Ереван или Белград на 6-ю неделю. Запустить релокационные бумаги сейчас. Это самое стратегически важное не-техническое действие.
- Цель: 1 000 GitHub stars + 5 active production users.

**Неделя 5 (cloud hosted demo + Web Bot Auth слой)**
- Поднять hosted dashboard на Railway/Fly.io (оба принимают карты РФ на 2026; Vercel — нет). Free tier с 7-дневным retention.
- Добавить Web Bot Auth signing layer в SDK. Опубликовать sample-директорию по `agentpassport.dev` (или твоему домену). Submit интеграцию в verified-bot directory Cloudflare.

**Неделя 6 (релокация + формализация)**
- Переехать физически в Ереван/Тбилиси/Белград. Заявка на residence card в работе. Открыть Wise/Revolut Business или локальный банк-аккаунт. Открыть Stripe Atlas на новом адресе.
- Продолжать шипать каждый день.

**Неделя 7 (выручка + кейс)**
- Выкатить paid tier ($29 starter / $199 team) на Lemon Squeezy или Paddle (избегай Stripe пока US C-Corp не живой). Цель: 3 платящих клиента (реальных, не друзей).
- Со-написать benchmark paper или технический кейс с одним из 5 production users. Получить публичную фразу «мы это используем». Это твой killer-quote для YC-заявки.

**Неделя 8 (подготовка YC-заявки)**
- Написать YC-заявку. Будь брутально честным про размер команды и локацию, и ruthlessly numerical про traction (stars, weekly active SDKs, paying logos, цифру бенчмарка).
- **Цель — батч F26 или W27, не S26.** Ontime-дедлайн S26 — 4 мая 2026 (завтра). Late S26 принимаются, но редко успешны для соло-фаундеров без prior batch exposure. F26 deadline обычно середина августа 2026 — это даёт ещё 4 месяца traction.
- Опционально: подайся на S26 **late** с тем, что есть сейчас — YC ревьюит late apps «когда есть свободное время», иногда в течение месяца. Если откажут, твоя F26-заявка резко сильнее.

### Три «tells» в ближайшие 4 недели, которые подтвердят или убьют ставку

1. **GitHub stars к концу недели 3.** Цель: 1 000+ за 14 дней с публичного запуска. **<300 = убивай**; категория агентной инфры горячая, что-то реально полезное доходит туда. (Browser Use — 0→50k за недели; первый OSS-запуск Laminar — 1.5k за дни; OpenClaw — 9k→210k за недели; планка реальная.)
2. **Named production user из YC-финансированной агентной компании к концу недели 4.** Конкретно: кто-то из Browser Use, Klavis, Lucidic, Hyperbrowser, Kernel, Stagehand, Skyvern, Abundant или Asteroid использует твой SDK во внутреннем тулинге и готов быть процитирован. **0 = убивай**; если ни один YC-backed билдер не парится, ни один YC-партнёр тоже не запарится.
3. **Cloudflare или AWS-инженер публично взаимодействует с твоей Web Bot Auth-имплементацией.** GitHub-issue, вопрос в Discord, ретвит в X. Web Bot Auth WG маленькая (DataDome, Cloudflare, Akamai, AWS, команда `agent.bot.goog` Google, ~250 IETF side-meeting attendees). **0 engagement = standards-смежный тезис не для тебя конкретно.**

Если все три зелёные: релоцируйся, полируй, подавайся на F26/W27, шанс реальный.
Если две из трёх зелёные: шипай всё равно, обращайся с OSS-stewardship как с целью, переосмысли VC-fit.
Если 0–1 из трёх зелёные: закрой проект на 4-недельной отметке, не трать вторую половину больничного. Бери что-то другое.

---

## Caveats и чего этот меморандум сказать не может

- **Цифры стареют быстро.** Счётчики MCP-серверов, GitHub stars и оценки funding round выше — на конец апреля 2026 из публичных источников.
- **Несколько «фактов» в широкой агентной экосистеме — vendor-published.** Цифра «97M monthly SDK downloads» — от Anthropic; «85% WebVoyager» — self-reported каждым вендором на разных тест-катах. Не доверяй head-to-head цифрам буквально.
- **Доступ founders из РФ к рынкам меняется месяц-в-месяц.** Прежде чем инкорпорироваться где-либо, консультируйся с реальным sanctions-юристом (на Кипре и в Армении есть фирмы, специализирующиеся на структурировании russian-tech-диаспоры).
- **YC F26 / W27 дедлайны пока не публичны.** Исторический паттерн: F26 applications открываются ~июль 2026, дедлайн ~середина августа, batch ~октябрь.
- **«Не сделают ли vision-based агенты всё это obsolete?» — реальная неопределённость.** Гэп 12–17 пунктов в надёжности до DOM-driven сужается. Твой клин — observability + replay + identity — самый **робастный** к этому коллапсу, потому что упавшие агентные runs нужно дебажить независимо от модальности восприятия.
- **Этот меморандум opinionated.** Рекомендация оптимизирует под: соло, Python-сильный, РФ-based, 4-недельное окно интенсивности, хочешь YC fit. Поменяй любое — ответ поменяется.
