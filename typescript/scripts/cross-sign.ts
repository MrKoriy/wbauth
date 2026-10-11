// Emit randomized signed requests as JSON (TS → Python check).
//   npx tsx typescript/scripts/cross-sign.ts 200 > /tmp/ts-signed.json
import { randomBytes } from "node:crypto";
import { ensureContentDigest } from "../src/adapters/_utils.js";
import { Identity, sign } from "../src/index.js";

let seed = 9421;
const rnd = () => {
	seed = (seed * 1103515245 + 12345) & 0x7fffffff;
	return seed / 0x7fffffff;
};
const pick = <T>(xs: T[]): T => xs[Math.floor(rnd() * xs.length)] as T;

const n = Number(process.argv[2] ?? 100);
const id = await Identity.fromTestKey(
	"https://agent.example/.well-known/http-message-signatures-directory",
);
const requests = [];
for (let i = 0; i < n; i++) {
	const host = pick(["example.com", "Crawltest.COM", "a.b.example.org", "[::1]", "127.0.0.1"]);
	const port = pick(["", "", ":443", ":8443"]);
	const path = `/${Array.from({ length: Math.floor(rnd() * 4) }, () => pick(["a", "b", "x-y", "%20"])).join("/")}`;
	const query = pick(["", "?q=1", "?a=b&c=d"]);
	const method = pick(["GET", "POST", "PUT", "PATCH", "DELETE"]);
	const body =
		method === "GET" || rnd() < 0.3 ? null : new Uint8Array(randomBytes(1 + Math.floor(rnd() * 64)));
	const url = `https://${host}${port}${path}${query}`;
	const headers: Record<string, string> = {};
	ensureContentDigest(method, headers, body);
	await sign({ method, url, headers, body }, id);
	requests.push({
		id: i,
		method,
		url,
		headers,
		body_b64: body ? Buffer.from(body).toString("base64") : null,
	});
}
process.stdout.write(JSON.stringify({ jwks: id.exportJwks(), requests }));
