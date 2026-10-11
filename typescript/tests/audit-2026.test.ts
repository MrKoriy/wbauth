// Regression suite for the Oct-2026 audit findings (see CHANGELOG 0.3.0).
import { readFileSync } from "node:fs";
import {
	createServer,
	type IncomingHttpHeaders,
	type IncomingMessage,
	type Server,
	type ServerResponse,
} from "node:http";
import type { AddressInfo } from "node:net";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { verify } from "web-bot-auth";
import { verifierFromJWK } from "web-bot-auth/crypto";
import { createSignedFetch, Identity, sign, VERSION } from "../src/index.js";

type Hit = {
	server: string;
	url: string;
	method: string;
	h: IncomingHttpHeaders;
	body: string;
};
const hits: Hit[] = [];
const servers: Server[] = [];

async function serve(
	name: string,
	host: string,
	handler: (req: IncomingMessage, res: ServerResponse) => void,
): Promise<string> {
	const s = createServer((req, res) => {
		let body = "";
		req.on("data", (c) => {
			body += c;
		});
		req.on("end", () => {
			const port = (s.address() as AddressInfo).port;
			hits.push({
				server: name,
				url: `http://${host}:${port}${req.url}`,
				method: req.method ?? "",
				h: req.headers,
				body,
			});
			handler(req, res);
		});
	});
	servers.push(s);
	await new Promise<void>((r) => s.listen(0, "127.0.0.1", r));
	return `http://${host}:${(s.address() as AddressInfo).port}`;
}

let A = "";
let B = "";
beforeAll(async () => {
	B = await serve("b", "127.0.0.1", (_req, res) => res.end("ok"));
	// "localhost" vs "127.0.0.1" → different @authority (and origin) per hop.
	A = await serve("a", "localhost", (req, res) => {
		const code = Number(
			new URL(req.url ?? "/", "http://x").searchParams.get("code") ?? 302,
		);
		if (req.url?.startsWith("/loop")) {
			res.writeHead(302, { location: "/loop" }).end();
			return;
		}
		res.writeHead(code, { location: `${B}/next` }).end();
	});
});
afterAll(() => {
	for (const s of servers) s.close();
});

async function isValid(id: Identity, hit: Hit): Promise<boolean> {
	const headers = new Headers();
	for (const [k, v] of Object.entries(hit.h)) {
		if (typeof v === "string") headers.set(k, v);
	}
	const jwk = id.exportJwks().keys[0] as JsonWebKey;
	const v = await verifierFromJWK(jwk);
	try {
		await verify(new Request(hit.url, { headers }), v);
		return true;
	} catch {
		return false;
	}
}

const newId = () => Identity.fromTestKey("https://agent.example/dir");

describe("createSignedFetch — redirects are re-signed per hop", () => {
	it("hop 2 carries a fresh, valid signature for its own authority", async () => {
		hits.length = 0;
		const id = await newId();
		const res = await createSignedFetch(id)(`${A}/start`);
		expect(res.status).toBe(200);
		expect(res.url).toBe(`${B}/next`);
		const [h1, h2] = hits;
		expect(h1?.server).toBe("a");
		expect(h2?.server).toBe("b");
		expect(h2?.h.signature).not.toBe(h1?.h.signature);
		expect(await isValid(id, h1 as Hit)).toBe(true);
		expect(await isValid(id, h2 as Hit)).toBe(true);
	});

	it("303 turns POST into a bodyless GET without content-digest", async () => {
		hits.length = 0;
		const id = await newId();
		await createSignedFetch(id)(`${A}/s?code=303`, {
			method: "POST",
			body: "x=1",
		});
		const h2 = hits.find((h) => h.server === "b") as Hit;
		expect(h2.method).toBe("GET");
		expect(h2.body).toBe("");
		expect(h2.h["content-digest"]).toBeUndefined();
		expect(h2.h["signature-input"]).not.toContain("content-digest");
	});

	it("307 keeps method and body, re-binding content-digest", async () => {
		hits.length = 0;
		const id = await newId();
		await createSignedFetch(id)(`${A}/s?code=307`, {
			method: "PUT",
			body: "payload",
		});
		const h2 = hits.find((h) => h.server === "b") as Hit;
		expect(h2.method).toBe("PUT");
		expect(h2.body).toBe("payload");
		expect(h2.h["signature-input"]).toContain("content-digest");
	});

	it("strips Authorization/Cookie on cross-origin hops", async () => {
		hits.length = 0;
		const id = await newId();
		await createSignedFetch(id)(`${A}/s`, {
			headers: { authorization: "Bearer secret", cookie: "a=b", "x-keep": "1" },
		});
		const h2 = hits.find((h) => h.server === "b") as Hit;
		expect(h2.h.authorization).toBeUndefined();
		expect(h2.h.cookie).toBeUndefined();
		expect(h2.h["x-keep"]).toBe("1");
	});

	it('redirect: "manual" returns the 3xx untouched', async () => {
		hits.length = 0;
		const id = await newId();
		const res = await createSignedFetch(id)(`${A}/s`, { redirect: "manual" });
		expect(res.status).toBe(302);
		expect(hits.filter((h) => h.server === "b")).toHaveLength(0);
	});

	it("enforces maxRedirects", async () => {
		const id = await newId();
		await expect(
			createSignedFetch(id, { maxRedirects: 3 })(`${A}/loop`),
		).rejects.toThrow(/redirect count exceeded/);
	});
});

describe("signer hardening", () => {
	it.each([
		0,
		-1,
		3601,
		Number.NaN,
		Number.POSITIVE_INFINITY,
	])("rejects expiresAfterSeconds=%s", async (secs) => {
		const id = await newId();
		await expect(
			sign(
				{ method: "GET", url: "https://s.example/", headers: {}, body: null },
				id,
				{ expiresAfterSeconds: secs },
			),
		).rejects.toThrow(RangeError);
	});

	it.each([
		"DELETE",
		"QUERY",
		"PATCH",
	])("binds %s bodies via content-digest", async (method) => {
		let captured: Record<string, string> = {};
		const id = await newId();
		const f = createSignedFetch(id, {
			fetch: (async (_u: RequestInfo | URL, init?: RequestInit) => {
				captured = init?.headers as Record<string, string>;
				return new Response("ok");
			}) as typeof fetch,
		});
		await f("https://s.example/x", { method, body: '{"id":1}' });
		expect(captured["Content-Digest"]).toMatch(/^sha-256=:/);
		expect(captured["Signature-Input"]).toContain("content-digest");
	});

	it("default-port URLs sign the bare host (parity with Python/Cloudflare)", async () => {
		const id = await newId();
		const a = await sign(
			{ method: "GET", url: "https://s.example:443/", headers: {}, body: null },
			id,
			{
				created: new Date(1_767_225_600_000),
				nonce:
					"dGVzdC1ub25jZS0wMS1maXhlZC0AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA==",
			},
		);
		const b = await sign(
			{ method: "GET", url: "https://s.example/", headers: {}, body: null },
			id,
			{
				created: new Date(1_767_225_600_000),
				nonce:
					"dGVzdC1ub25jZS0wMS1maXhlZC0AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA==",
			},
		);
		expect(a.signature).toBe(b.signature);
	});

	it("produces a fresh nonce per request", async () => {
		const id = await newId();
		const r = () =>
			sign(
				{ method: "GET", url: "https://s.example/", headers: {}, body: null },
				id,
			);
		expect((await r()).signatureInput).not.toBe((await r()).signatureInput);
	});
});

it("VERSION matches package.json", () => {
	const pkg = JSON.parse(
		readFileSync(new URL("../package.json", import.meta.url), "utf8"),
	);
	expect(VERSION).toBe(pkg.version);
});
