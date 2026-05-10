/**
 * applyTo — Playwright async helper for Web Bot Auth (ADAPT-05).
 *
 * Mirrors python/src/wbauth/adapters/playwright.py. Registers a route
 * handler that intercepts every outgoing request, signs it via wbauth.sign(),
 * and continues with the signed headers.
 *
 * Pitfall 3: Call applyTo(page, identity) BEFORE the first page.goto()/click
 * that should produce signed requests. page.route must be registered before
 * navigation begins, or the navigation request leaves the browser unsigned.
 *
 * Pitfall (iframe coverage): page.route('**\/*', handler) covers all
 * sub-frame requests by default. If the target site uses Service Workers,
 * set serviceWorkers="block" on the BrowserContext (Playwright option).
 *
 * Note: `playwright` is a peerDependency (optional). End users only install
 * it if they actually use this adapter — fetch-only consumers pay zero cost.
 */
import type { Page, Request as PWRequest, Route } from "playwright";
import type { Identity } from "../identity.js";
import { sign } from "../signer.js";
import { ensureContentDigest } from "./_utils.js";

export async function applyTo(page: Page, identity: Identity): Promise<void> {
  await page.route("**/*", async (route: Route, request: PWRequest) => {
    const headers = await request.allHeaders();
    const postData = request.postDataBuffer();
    const body = postData ? new Uint8Array(postData) : null;

    ensureContentDigest(request.method(), headers, body);

    await sign(
      { method: request.method(), url: request.url(), headers, body },
      identity,
    );

    if (
      identity.userAgent &&
      !Object.keys(headers).some((k) => k.toLowerCase() === "user-agent")
    ) {
      headers["User-Agent"] = identity.userAgent;
    }

    await route.continue({ headers });
  });
}
