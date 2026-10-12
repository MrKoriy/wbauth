import { sign as edSign, generateKeyPairSync } from "node:crypto";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { makeSignDecider } from "../src/adapters/_utils.js";
import { createSignedFetch } from "../src/adapters/fetch.js";
import { Identity, validateSignatureAgentUrl } from "../src/identity.js";
import { sign } from "../src/signer.js";
import { NonceStore, VerificationError, Verifier } from "../src/verifier.js";

const AGENT =
	"https://agent.example/.well-known/http-message-signatures-directory";
const tmp = () => mkdtemp(join(tmpdir(), "wbauth-"));

async function signedRequest(id: Identity, url = "https://site.example/p") {
	const headers: Record<string, string> = {};
	await sign({ method: "GET", url, headers, body: null }, id);
	return new Request(url, { headers });
}

describe("#1 private key never serialised", () => {
	it("JSON.stringify / String exclude private material", async () => {
		const id = await Identity.fromTestKey(AGENT);
		const json = JSON.stringify(id);
		expect(json).not.toMatch(/"d"/);
		expect(String(id)).toContain("REDACTED");
		expect(JSON.stringify(id.exportJwks())).not.toMatch(/"d"/);
	});
});

describe("#2 Signature-Agent validation", () => {
	it.each([
		'https://a.example/x",evil="1',
		"https://a.example/\r\nX: y",
		"http://a.example/",
		"https://",
		"https://a.example/ space",
	])("rejects %s", (u) => {
		expect(() => validateSignatureAgentUrl(u)).toThrow();
	});
	it("accepts a normal URL", () => {
		expect(validateSignatureAgentUrl(AGENT)).toBe(AGENT);
	});
});

describe("#8 signing scope", () => {
	it("http unsigned by default; hosts allow-list with wildcards", () => {
		const d = makeSignDecider({ hosts: ["*.example.com", "api.test"] });
		expect(d("https://a.example.com/")).toBe(true);
		expect(d("https://api.test/")).toBe(true);
		expect(d("https://evil.test/")).toBe(false);
		expect(d("http://a.example.com/")).toBe(false);
		expect(makeSignDecider({ allowInsecure: true })("http://x.test/")).toBe(
			true,
		);
	});
	it("fetch adapter does not sign out-of-scope hosts", async () => {
		const id = await Identity.fromTestKey(AGENT);
		let seen: Headers | undefined;
		const f = createSignedFetch(id, {
			hosts: ["allowed.example"],
			fetch: (async (_u: RequestInfo | URL, init?: RequestInit) => {
				seen = new Headers(init?.headers);
				return new Response("ok");
			}) as typeof fetch,
		} as never);
		await f("https://other.example/", {
			headers: { Signature: "stale", "Signature-Input": "stale" },
		});
		expect(seen?.get("signature")).toBeNull();
		expect(seen?.get("signature-input")).toBeNull();
	});
});

describe("#23 Verifier", () => {
	it("accepts a valid signature, rejects replay and tampering", async () => {
		const id = await Identity.fromTestKey(AGENT);
		const v = new Verifier({ keyResolver: async () => id.publicJwk });
		const req = await signedRequest(id);
		const agent = await v.verify(req);
		expect(agent.kid).toBe(id.kid);
		expect(agent.signatureAgentUrl).toBe(AGENT);
		await expect(v.verify(req)).rejects.toBeInstanceOf(VerificationError);

		const req2 = await signedRequest(id);
		const tampered = new Request("https://other.example/p", {
			headers: req2.headers,
		});
		await expect(
			new Verifier({ keyResolver: async () => id.publicJwk }).verify(tampered),
		).rejects.toThrow();
	});
	it("rejects unsigned and expired requests", async () => {
		const id = await Identity.fromTestKey(AGENT);
		const v = new Verifier({ keyResolver: async () => id.publicJwk });
		await expect(
			v.verify(new Request("https://site.example/")),
		).rejects.toThrow(/not signed/);
		const req = await signedRequest(id);
		await expect(
			v.verify(req, { now: Math.floor(Date.now() / 1000) + 3600 }),
		).rejects.toThrow();
	});
	it("NonceStore detects duplicates", () => {
		const s = new NonceStore();
		const exp = Math.floor(Date.now() / 1000) + 60;
		expect(s.seen("n", exp)).toBe(false);
		expect(s.seen("n", exp)).toBe(true);
	});
});

describe("#3/#11/#24 key storage", () => {
	it("generate never overwrites an existing key", async () => {
		const p = join(await tmp(), "k.pem");
		await Identity.generate(p, { signatureAgentUrl: AGENT });
		await expect(
			Identity.generate(p, { signatureAgentUrl: AGENT }),
		).rejects.toThrow();
	});
	it("persisted keyring rotation keeps the retiring key in JWKS", async () => {
		const dir = await tmp();
		const a = await Identity.loadKeyring(dir, { signatureAgentUrl: AGENT });
		const b = await a.rotateKeyring(dir);
		expect(b.kid).not.toBe(a.kid);
		const reloaded = await Identity.loadKeyring(dir, {
			signatureAgentUrl: AGENT,
		});
		expect(reloaded.kid).toBe(b.kid);
		expect(reloaded.exportJwks().keys.map((k) => k.kid)).toEqual([
			b.kid,
			a.kid,
		]);
	});
	it("encrypted PEM round-trips and needs the password", async () => {
		const p = join(await tmp(), "enc.pem");
		const a = await Identity.generate(p, {
			signatureAgentUrl: AGENT,
			password: "s3cret",
		} as never);
		expect(await readFile(p, "utf8")).toContain("ENCRYPTED");
		const b = await Identity.load(p, {
			signatureAgentUrl: AGENT,
			password: "s3cret",
		} as never);
		expect(b.kid).toBe(a.kid);
		await expect(
			Identity.load(p, { signatureAgentUrl: AGENT }),
		).rejects.toThrow();
	});
	it("fromSigner wraps an external backend", async () => {
		const { privateKey, publicKey } = generateKeyPairSync("ed25519");
		const id = await Identity.fromSigner(
			{
				publicJwk: publicKey.export({ format: "jwk" }) as JsonWebKey,
				sign: (data) => new Uint8Array(edSign(null, data, privateKey)),
			},
			{ signatureAgentUrl: AGENT },
		);
		const v = new Verifier({ keyResolver: async () => id.publicJwk });
		expect((await v.verify(await signedRequest(id))).kid).toBe(id.kid);
	});
	it("garbage key file is rejected", async () => {
		const p = join(await tmp(), "bad.pem");
		await writeFile(p, "not a key");
		await expect(
			Identity.load(p, { signatureAgentUrl: AGENT }),
		).rejects.toThrow();
	});
});
