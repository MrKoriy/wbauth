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
import {
	applyUserAgent,
	ensureContentDigest,
	makeSignDecider,
	type SignScopeOptions,
} from "./_utils.js";

export interface ApplyToOptions extends SignScopeOptions {
	/** Route pattern passed to `page.route`. Default `"**\/*"`. */
	pattern?: string;
}

export async function applyTo(
	page: Page,
	identity: Identity,
	options: ApplyToOptions = {},
): Promise<() => Promise<void>> {
	const pattern = options.pattern ?? "**/*";
	const decide = makeSignDecider(options);

	const handler = async (route: Route, request: PWRequest) => {
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
	};
	await page.route(pattern, handler);
	/** Detach: remove the signing route handler. */
	return async () => {
		await page.unroute(pattern, handler);
	};
}
