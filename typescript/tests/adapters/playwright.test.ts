/**
 * applyTo (Playwright adapter) unit tests (Phase 4 Plan 01 Task 3).
 *
 * Mirrors python/tests/test_adapters_playwright.py — vi.fn fake page.route
 * captures the registered handler so tests can invoke it with mock Route +
 * Request objects, no live browser binary required (D-65).
 */
import { describe, expect, it, vi } from "vitest";
import { Identity } from "../../src/identity.js";
import { applyTo } from "../../src/adapters/playwright.js";

interface RegisteredHandler {
  // biome-ignore lint/suspicious/noExplicitAny: mocks fake the Playwright Route/Request types
  (route: any, request: any): Promise<void>;
}

function fakePage() {
  let registeredHandler: RegisteredHandler | null = null;
  // biome-ignore lint/suspicious/noExplicitAny: vi.fn loose typing is fine for a mock
  const route = vi.fn(async (_pattern: string, handler: any) => {
    registeredHandler = handler;
  });
  return {
    // biome-ignore lint/suspicious/noExplicitAny: structural mock substitutes for the Page type
    page: { route } as any,
    // biome-ignore lint/suspicious/noExplicitAny: invoke takes mock route + request
    invoke: async (mockRoute: any, mockRequest: any) => {
      if (!registeredHandler) {
        throw new Error("applyTo did not call page.route");
      }
      await registeredHandler(mockRoute, mockRequest);
    },
  };
}

describe("applyTo", () => {
  it("registers page.route('**/*', handler)", async () => {
    const id = await Identity.fromTestKey("https://example.com/agent.json");
    const { page } = fakePage();
    await applyTo(page, id);
    expect(page.route).toHaveBeenCalledWith("**/*", expect.any(Function));
  });

  it("signs GET request and continues with signed headers", async () => {
    const id = await Identity.fromTestKey("https://example.com/agent.json");
    const { page, invoke } = fakePage();
    await applyTo(page, id);
    const continueSpy = vi.fn(async () => {});
    await invoke(
      { continue: continueSpy },
      {
        method: () => "GET",
        url: () => "https://api.example.com/",
        allHeaders: async () => ({}),
        postDataBuffer: () => null,
      },
    );
    expect(continueSpy).toHaveBeenCalledOnce();
    const callArg = continueSpy.mock.calls[0]![0] as {
      headers: Record<string, string>;
    };
    const { headers } = callArg;
    expect(headers["Signature"]).toMatch(/^sig1=:.+:$/);
    expect(headers["Signature-Input"]).toContain('tag="web-bot-auth"');
    expect(headers["Signature-Agent"]).toBe('"https://example.com/agent.json"');
  });

  it("auto-computes Content-Digest for POST + body", async () => {
    const id = await Identity.fromTestKey("https://example.com/agent.json");
    const { page, invoke } = fakePage();
    await applyTo(page, id);
    const continueSpy = vi.fn(async () => {});
    const buf = Buffer.from("hello-from-playwright");
    await invoke(
      { continue: continueSpy },
      {
        method: () => "POST",
        url: () => "https://api.example.com/",
        allHeaders: async () => ({}),
        postDataBuffer: () => buf,
      },
    );
    const callArg = continueSpy.mock.calls[0]![0] as {
      headers: Record<string, string>;
    };
    const { headers } = callArg;
    expect(headers["Content-Digest"]).toMatch(/^sha-256=:.+:$/);
    expect(headers["Signature-Input"]).toContain("content-digest");
  });

  it("statelessness — two requests through same page produce different nonces", async () => {
    const id = await Identity.fromTestKey("https://example.com/agent.json");
    const { page, invoke } = fakePage();
    await applyTo(page, id);
    const continueSpy = vi.fn(async () => {});
    const mockReq = {
      method: () => "GET",
      url: () => "https://x/",
      allHeaders: async () => ({}),
      postDataBuffer: () => null,
    };
    await invoke({ continue: continueSpy }, mockReq);
    await invoke({ continue: continueSpy }, mockReq);
    const h1 = (
      continueSpy.mock.calls[0]![0] as { headers: Record<string, string> }
    ).headers["Signature-Input"];
    const h2 = (
      continueSpy.mock.calls[1]![0] as { headers: Record<string, string> }
    ).headers["Signature-Input"];
    expect(h1).not.toBe(h2);
  });

  it("UA injection only when caller did NOT set one", async () => {
    const id = await Identity.fromTestKey("https://example.com/agent.json");
    // Backdoor: userAgent is `readonly` on the type but assignable here for testing.
    (id as unknown as { userAgent: string }).userAgent = "wbauth-test/1.0";
    const { page, invoke } = fakePage();
    await applyTo(page, id);

    const continueSpy = vi.fn(async () => {});
    await invoke(
      { continue: continueSpy },
      {
        method: () => "GET",
        url: () => "https://x/",
        allHeaders: async () => ({}),
        postDataBuffer: () => null,
      },
    );
    const headers0 = (
      continueSpy.mock.calls[0]![0] as { headers: Record<string, string> }
    ).headers;
    expect(headers0["User-Agent"]).toBe("wbauth-test/1.0");

    continueSpy.mockClear();
    await invoke(
      { continue: continueSpy },
      {
        method: () => "GET",
        url: () => "https://x/",
        allHeaders: async () => ({ "user-agent": "caller/2" }),
        postDataBuffer: () => null,
      },
    );
    const headers1 = (
      continueSpy.mock.calls[0]![0] as { headers: Record<string, string> }
    ).headers;
    // Caller-supplied UA preserved; identity.userAgent NOT injected.
    expect(headers1["User-Agent"]).toBeUndefined();
    expect(headers1["user-agent"]).toBe("caller/2");
  });
});
