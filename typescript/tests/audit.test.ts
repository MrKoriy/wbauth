/**
 * Audit regression tests (2026-10 audit).
 *
 * `it(...)` = confirmed defect: the assertion describes the DESIRED
 * behaviour and currently fails. When the bug is fixed vitest reports the
 * test as failing → flip it to a plain `it(...)`.
 */
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createSignedFetch } from "../src/adapters/fetch.js";
import { applyTo } from "../src/adapters/playwright.js";
import { Identity } from "../src/identity.js";
import { sign } from "../src/signer.js";

const PKG_DIR = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const AGENT = "https://example.com/agent.json";

let captured: { url: string; init?: RequestInit }[];
let fetchSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
	captured = [];
	fetchSpy = vi
		.spyOn(globalThis, "fetch")
		.mockImplementation(async (url, init) => {
			captured.push({ url: String(url), init });
			return new Response(null, { status: 200 });
		});
});
afterEach(() => fetchSpy.mockRestore());

/** Merge a plain-object header bag the way fetch() would (case-insensitive). */
function wire(init?: RequestInit): Headers {
	return new Headers(init?.headers as Record<string, string>);
}

describe("packaging", () => {
	const dist = resolve(PKG_DIR, "dist", "index.cjs");
	it.skipIf(!existsSync(dist))(
		"CommonJS require() returns the public API (dist/index.cjs)",
		() => {
			const out = execFileSync(
				process.execPath,
				[
					"-e",
					`const m=require(${JSON.stringify(dist)});process.stdout.write(typeof m.Identity)`,
				],
				{ encoding: "utf8" },
			);
			expect(out).toBe("function");
		},
	);
});

describe("createSignedFetch", () => {
	it("re-sending an already-signed Request yields ONE signature, not two merged ones", async () => {
		const id = await Identity.fromTestKey(AGENT);
		const sf = createSignedFetch(id);
		await sf("https://api.example.com/x");
		// Simulate a retry wrapper that re-sends the previous request's headers.
		await sf("https://api.example.com/x", { headers: wire(captured[0].init) });
		const h = wire(captured[1].init);
		expect(h.get("signature")?.split("sig1=").length).toBe(2);
		expect(h.get("signature-agent")).toBe(`"${AGENT}"`);
	});

	it("AbortSignal from a Request object is forwarded to fetch", async () => {
		const id = await Identity.fromTestKey(AGENT);
		const sf = createSignedFetch(id);
		const ac = new AbortController();
		await sf(new Request("https://api.example.com/x", { signal: ac.signal }));
		expect(captured[0].init?.signal).toBeDefined();
	});

	it("redirect mode from a Request object is preserved", async () => {
		const id = await Identity.fromTestKey(AGENT);
		const sf = createSignedFetch(id);
		await sf(new Request("https://api.example.com/x", { redirect: "manual" }));
		expect(captured[0].init?.redirect).toBe("manual");
	});

	it("signs POST bodies with content-digest covered", async () => {
		const id = await Identity.fromTestKey(AGENT);
		const sf = createSignedFetch(id);
		await sf("https://api.example.com/x", { method: "POST", body: '{"a":1}' });
		const h = wire(captured[0].init);
		expect(h.get("content-digest")).toMatch(/^sha-256=:.+:$/);
		expect(h.get("signature-input")).toContain('"content-digest"');
	});
});

describe("sign()", () => {
	it("rejects non-positive expiresAfterSeconds (parity target for Python)", async () => {
		const id = await Identity.fromTestKey(AGENT);
		await expect(
			sign(
				{ method: "GET", url: "https://a.example/", headers: {}, body: null },
				id,
				{
					expiresAfterSeconds: -1,
				},
			),
		).rejects.toThrow();
	});

	it("POST body without Content-Digest must throw (Python does) instead of covering a missing header", async () => {
		const id = await Identity.fromTestKey(AGENT);
		const req = {
			method: "POST",
			url: "https://a.example/",
			headers: {} as Record<string, string>,
			body: new TextEncoder().encode("x"),
		};
		let threw = false;
		try {
			await sign(req, id);
		} catch {
			threw = true;
		}
		// Either throw, or auto-add the digest. Silently covering a missing header is the bug.
		expect(threw || "Content-Digest" in req.headers).toBe(true);
	});
});

describe("User-Agent", () => {
	it("replaces runtime default UA with Identity.userAgent", async () => {
		const id = await Identity.fromTestKey(AGENT, { userAgent: "MyBot/1.0" });
		const sf = createSignedFetch(id);
		await sf("https://api.example.com/x", {
			headers: { "user-agent": "node" },
		});
		expect(wire(captured[0].init).get("user-agent")).toBe("MyBot/1.0");
		await sf("https://api.example.com/x", {
			headers: { "user-agent": "Custom/2" },
		});
		expect(wire(captured[1].init).get("user-agent")).toBe("Custom/2");
	});
});

describe("sign() header hygiene", () => {
	it("replaces stale lower-case Signature* headers instead of duplicating", async () => {
		const id = await Identity.fromTestKey(AGENT);
		const headers: Record<string, string> = {
			signature: "sig1=:old:",
			"signature-input": "sig1=()",
			"signature-agent": '"https://old.example/"',
		};
		await sign(
			{ method: "GET", url: "https://a.example/", headers, body: null },
			id,
		);
		const keys = Object.keys(headers).map((k) => k.toLowerCase());
		expect(keys.filter((k) => k === "signature")).toHaveLength(1);
		expect(headers["Signature-Agent"]).toBe(`"${AGENT}"`);
		expect(headers.Signature).not.toBe("sig1=:old:");
	});
});

describe("applyTo host scoping", () => {
	type Handler = (route: unknown, request: unknown) => Promise<void>;
	async function setup(opts?: Parameters<typeof applyTo>[2]) {
		let handler: Handler | undefined;
		const page = {
			route: vi.fn(async (_p: string, h: Handler) => {
				handler = h;
			}),
		};
		const id = await Identity.fromTestKey(AGENT);
		await applyTo(page as never, id, opts);
		return async (url: string) => {
			const cont = vi.fn(
				async (_o?: { headers: Record<string, string> }) => {},
			);
			const fallback = vi.fn(async () => {});
			await handler?.(
				{ continue: cont, fallback },
				{
					method: () => "GET",
					url: () => url,
					allHeaders: async () => ({}),
					postDataBuffer: () => null,
				},
			);
			return { cont, fallback };
		};
	}

	it("signs only allow-listed hosts and falls back for the rest", async () => {
		const send = await setup({ hosts: ["*.example.com"] });
		const a = await send("https://www.example.com/");
		expect(a.cont.mock.calls[0]?.[0]?.headers.Signature).toBeTruthy();
		const b = await send("https://cdn.tracker.net/x.js");
		expect(b.fallback).toHaveBeenCalledOnce();
		expect(b.cont).not.toHaveBeenCalled();
	});

	it("never signs non-http(s) URLs", async () => {
		const send = await setup();
		const r = await send("data:text/plain,hi");
		expect(r.fallback).toHaveBeenCalledOnce();
	});
});
