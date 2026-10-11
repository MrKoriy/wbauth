// Verify requests signed by the Python SDK (Python → TS check).
//   npx tsx typescript/scripts/cross-verify.ts /tmp/py-signed.json
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { verify } from "web-bot-auth";
import { verifierFromJWK } from "web-bot-auth/crypto";

type Signed = {
	id: number;
	method: string;
	url: string;
	headers: Record<string, string>;
	body_b64: string | null;
};
const data = JSON.parse(readFileSync(process.argv[2] as string, "utf8")) as {
	jwks: { keys: (JsonWebKey & { kid: string })[] };
	requests: Signed[];
};
const verifiers = new Map<string, Awaited<ReturnType<typeof verifierFromJWK>>>();
for (const k of data.jwks.keys) verifiers.set(k.kid, await verifierFromJWK(k));

let failures = 0;
for (const r of data.requests) {
	try {
		const headers = new Headers(r.headers);
		await verify(
			new Request(r.url, { method: r.method === "GET" ? "GET" : r.method, headers }),
			async (d, s, p) => {
				const v = verifiers.get(p.keyid);
				if (!v) throw new Error(`unknown keyid ${p.keyid}`);
				return v(d, s, p);
			},
			{ now: () => new Date() } as never,
		);
		if (r.body_b64) {
			const want = `sha-256=:${createHash("sha256").update(Buffer.from(r.body_b64, "base64")).digest("base64")}:`;
			if (headers.get("content-digest") !== want) throw new Error("content-digest mismatch");
			if (!headers.get("signature-input")?.includes("content-digest"))
				throw new Error("content-digest not covered");
		}
	} catch (e) {
		failures++;
		console.error(`FAIL #${r.id} ${r.method} ${r.url}: ${e}`);
	}
}
console.log(`typescript verified ${data.requests.length - failures}/${data.requests.length} Python-signed requests`);
process.exit(failures ? 1 : 0);
