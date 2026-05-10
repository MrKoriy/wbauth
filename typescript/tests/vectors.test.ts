/**
 * Cross-language byte-equality vector tests (IDENT-04, TypeScript side).
 *
 * Loads the same `spec/test-vectors/*` directories as the Python pytest suite
 * (`python/tests/test_vectors.py`) and asserts that the Cloudflare-vendored
 * `web-bot-auth` 0.1.3 npm package produces byte-identical Signature-Input
 * and Signature header values.
 *
 * Multi-key vectors (vectors with `retiring_key_jwk`) are skipped here at the
 * raw web-bot-auth signer level — that lib only exposes a single-Signer API.
 * The full multi-key Identity rotation oracle moved to
 * `tests/identity-multikey.test.ts` (Plan 04-02), which exercises
 * Identity.rotate() + exportJwks() ordering against vector 04. The Python
 * side (`test_vector_jwks_full_for_multi_key`) covers the JWKS export oracle
 * end-to-end from the Python SDK.
 */
import { describe, expect, it } from "vitest";
import {
	REQUEST_COMPONENTS,
	REQUEST_COMPONENTS_WITHOUT_SIGNATURE_AGENT,
	signatureHeaders,
} from "web-bot-auth";
import { signerFromJWK } from "web-bot-auth/crypto";

import { loadAllVectors } from "./helpers";

const vectors = loadAllVectors();

describe("cross-language byte-equality vectors (IDENT-04)", () => {
	for (const v of vectors) {
		if (v.input.identity.retiring_key_jwk) {
			// Multi-key Identity oracle lives in tests/identity-multikey.test.ts
			// (Plan 04-02). The raw web-bot-auth Signer API is single-key, so the
			// signer-level vector loop here cannot reproduce a 2-key JWKS;
			// the SDK-level Identity API can.
			it.skip(`${v.name} (multi-key — see identity-multikey.test.ts)`, () => {});
			continue;
		}

		it(`${v.name}: produces byte-equal Signature-Input + Signature`, async () => {
			const jwk = v.input.identity.private_key_jwk;
			const signer = await signerFromJWK(jwk);

			// Build a Request that mirrors the Python signer's input. The Python
			// signer mutates `request.headers["Signature-Agent"]` BEFORE building
			// the signing base; the TS library does the same when the
			// signature-agent header is present on the input message. We pre-set
			// it here so both runtimes hash identical bytes.
			const headers = new Headers();
			for (const [k, val] of Object.entries(
				v.input.request.headers as Record<string, string>,
			)) {
				headers.set(k, val);
			}
			headers.set(
				"Signature-Agent",
				`"${v.input.identity.signature_agent_url}"`,
			);

			const init: RequestInit = {
				method: v.input.request.method,
				headers,
			};
			if (v.input.request.body) {
				// Buffer.from on a base64 string yields a Uint8Array — Request accepts BodyInit.
				init.body = Buffer.from(v.input.request.body, "base64");
			}
			const req = new Request(v.input.request.url, init);

			// Pick the components: web-bot-auth 0.1.3's getSigningOptions defaults
			// to REQUEST_COMPONENTS when signature-agent is on the message and
			// REQUEST_COMPONENTS_WITHOUT_SIGNATURE_AGENT otherwise. For vectors
			// that include "content-digest" in covered_components, we have to
			// pass `components` explicitly (the library's defaults don't include it).
			const requestedComponents = v.input.signing_params.covered_components;
			let components: string[] | undefined;
			const looksLikeDefaultWithAgent =
				requestedComponents.length === 2 &&
				requestedComponents[0] === "@authority" &&
				requestedComponents[1] === "signature-agent";
			const looksLikeDefaultWithoutAgent =
				requestedComponents.length === 1 &&
				requestedComponents[0] === "@authority";
			if (looksLikeDefaultWithAgent) {
				components = REQUEST_COMPONENTS as string[];
			} else if (looksLikeDefaultWithoutAgent) {
				components = REQUEST_COMPONENTS_WITHOUT_SIGNATURE_AGENT as string[];
			} else {
				components = requestedComponents;
			}

			const params = {
				created: new Date(v.input.signing_params.created * 1000),
				expires: new Date(
					(v.input.signing_params.created +
						v.input.signing_params.expires_after_seconds) *
						1000,
				),
				nonce: v.input.signing_params.nonce,
				key: v.input.signing_params.label,
				components,
			};

			const result = await signatureHeaders(req, signer, params);

			expect(result["Signature-Input"]).toBe(v.expected.signature_input_value);
			expect(result.Signature).toBe(v.expected.signature_value);
		});
	}
});
