/**
 * applyTo — sign every matching request a Playwright page sends.
 *
 * Mirrors python/src/wbauth/adapters/playwright.py.
 *
 * Privacy: by default every http(s) request is signed, including third-party
 * analytics/CDN hosts, which reveals your agent identity to them. Pass
 * `hosts` to restrict signing to the sites you actually target:
 *
 *   await applyTo(page, identity, { hosts: ["example.com", "*.example.org"] });
 *
 * Non-http(s) requests (data:, blob:, chrome-extension:) are never signed.
 * Note: Playwright disables the HTTP cache while a route is active.
 */
import type { Page, Request as PWRequest, Route } from "playwright";
import type { Identity } from "../identity.js";
import { sign } from "../signer.js";
import { applyUserAgent, ensureContentDigest, hostMatches } from "./_utils.js";

export interface ApplyToOptions {
	/** Only sign requests to these hosts (`example.com`, `*.example.com`). */
	hosts?: readonly string[];
	/** Custom predicate; takes precedence over `hosts`. */
	shouldSign?: (url: URL) => boolean;
	/** Route pattern passed to `page.route`. Default `"**\/*"`. */
	pattern?: string;
}

export async function applyTo(
	page: Page,
	identity: Identity,
	options: ApplyToOptions = {},
): Promise<void> {
	const pattern = options.pattern ?? "**/*";
	const decide = (raw: string): boolean => {
		let u: URL;
		try {
			u = new URL(raw);
		} catch {
			return false;
		}
		if (u.protocol !== "https:" && u.protocol !== "http:") return false;
		if (options.shouldSign) return options.shouldSign(u);
		if (options.hosts) return hostMatches(u.hostname, options.hosts);
		return true;
	};

	await page.route(pattern, async (route: Route, request: PWRequest) => {
		const url = request.url();
		if (!decide(url)) {
			const r = route as Route & { fallback?: () => Promise<void> };
			await (r.fallback ? r.fallback() : route.continue());
			return;
		}
		const headers = await request.allHeaders();
		const postData = request.postDataBuffer();
		const body = postData ? new Uint8Array(postData) : null;
		ensureContentDigest(request.method(), headers, body);
		await sign({ method: request.method(), url, headers, body }, identity);
		applyUserAgent(headers, identity.userAgent);
		await route.continue({ headers });
	});
}
