/**
 * createSignedFetch unit tests (Phase 4 Plan 01 Task 2).
 *
 * Mirrors python/tests/test_adapters_httpx.py — same behaviors:
 * - Returned value matches `typeof fetch` (URL-string + init).
 * - Outgoing request carries Signature, Signature-Input, Signature-Agent.
 * - Stateless: two consecutive calls produce different nonces.
 * - Auto-Content-Digest for POST + body; preserves caller-supplied digest.
 * - Does NOT add Content-Digest for GET.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createSignedFetch } from "../../src/adapters/fetch.js";
import { Identity } from "../../src/identity.js";

let fetchSpy: ReturnType<typeof vi.spyOn>;
let captured: { url: string; init?: RequestInit }[];

beforeEach(() => {
	captured = [];
	fetchSpy = vi
		.spyOn(globalThis, "fetch")
		.mockImplementation(async (url, init) => {
			captured.push({ url: String(url), init });
			return new Response(null, { status: 200 });
		});
});

afterEach(() => {
	fetchSpy.mockRestore();
});

describe("createSignedFetch", () => {
	it("returned function is typeof fetch (accepts URL string + init)", async () => {
		const id = await Identity.fromTestKey("https://example.com/agent.json");
		const sf = createSignedFetch(id);
		const res = await sf("https://api.example.com/data");
		expect(res.status).toBe(200);
	});

	it("attaches Signature, Signature-Input, Signature-Agent to outgoing request", async () => {
		const id = await Identity.fromTestKey("https://example.com/agent.json");
		const sf = createSignedFetch(id);
		await sf("https://api.example.com/data");
		const headers = (captured[0]?.init?.headers ?? {}) as Record<
			string,
			string
		>;
		expect(headers.Signature).toMatch(/^sig1=:.+:$/);
		expect(headers["Signature-Input"]).toContain('tag="web-bot-auth"');
		expect(headers["Signature-Agent"]).toBe('"https://example.com/agent.json"');
	});

	it("statelessness: two consecutive calls produce different nonces", async () => {
		const id = await Identity.fromTestKey("https://example.com/agent.json");
		const sf = createSignedFetch(id);
		await sf("https://api.example.com/a");
		await sf("https://api.example.com/b");
		const n1 = (captured[0]?.init?.headers as Record<string, string>)[
			"Signature-Input"
		];
		const n2 = (captured[1]?.init?.headers as Record<string, string>)[
			"Signature-Input"
		];
		expect(n1).not.toBe(n2);
	});

	it("auto-computes Content-Digest for POST with body", async () => {
		const id = await Identity.fromTestKey("https://example.com/agent.json");
		const sf = createSignedFetch(id);
		await sf("https://api.example.com/data", { method: "POST", body: "hello" });
		const headers = (captured[0]?.init?.headers ?? {}) as Record<
			string,
			string
		>;
		expect(headers["Content-Digest"]).toMatch(/^sha-256=:[A-Za-z0-9+/=]+:$/);
	});

	it("preserves caller-supplied Content-Digest", async () => {
		const id = await Identity.fromTestKey("https://example.com/agent.json");
		const sf = createSignedFetch(id);
		const ours = "sha-256=:CALLER_DIGEST==:";
		await sf("https://api.example.com/data", {
			method: "POST",
			body: "hello",
			headers: { "Content-Digest": ours },
		});
		const headers = (captured[0]?.init?.headers ?? {}) as Record<
			string,
			string
		>;
		// Header may be lowercased by the Request normalization; check both.
		const got = headers["Content-Digest"] ?? headers["content-digest"];
		expect(got).toBe(ours);
	});

	it("does NOT add Content-Digest for GET", async () => {
		const id = await Identity.fromTestKey("https://example.com/agent.json");
		const sf = createSignedFetch(id);
		await sf("https://api.example.com/data");
		const headers = (captured[0]?.init?.headers ?? {}) as Record<
			string,
			string
		>;
		expect(headers["Content-Digest"]).toBeUndefined();
		expect(headers["content-digest"]).toBeUndefined();
	});
});
