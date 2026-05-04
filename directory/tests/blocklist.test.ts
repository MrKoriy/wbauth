// Per D-43, D-44 + Security Task #3 (V4 ASVS — false-positive guard).
//
// The blocklist's job is to stop drive-by impersonation of major bot names
// (Googlebot, OpenAIBot, ChatGPT-Crawler, etc.) at registration time. The
// false-positive guard ensures legitimate names that happen to contain a
// reserved token (e.g. "googlestyle-app") are still allowed.
import { describe, it, expect } from "vitest";
import { isReservedName } from "../src/blocklist";

describe("isReservedName (D-43)", () => {
  it("returns the matched token for an exact case-insensitive reserved name", () => {
    expect(isReservedName("google")).toBe("google");
    expect(isReservedName("Google")).toBe("google");
    expect(isReservedName("GOOGLE")).toBe("google");
  });

  it("blocks substring + bot suffix", () => {
    expect(isReservedName("openai-bot")).toBe("openai");
    expect(isReservedName("OpenAIBot")).toBe("openai");
  });

  it("blocks substring + agent suffix", () => {
    expect(isReservedName("googleagent")).toBe("google");
    expect(isReservedName("AmazonAgent")).toBe("amazon");
  });

  it("blocks substring + crawler suffix", () => {
    expect(isReservedName("ChatGPT-Crawler-anthropic")).toBe("anthropic");
  });

  it("V4 ASVS false-positive guard: 'googlestyle-app' is allowed", () => {
    // Contains 'google' substring but no bot/agent/crawler suffix.
    expect(isReservedName("googlestyle-app")).toBeNull();
  });

  it("name with bot suffix but no reserved token is allowed", () => {
    expect(isReservedName("legitimate-bot")).toBeNull();
    expect(isReservedName("MyAgent")).toBeNull();
    expect(isReservedName("ResearchCrawler")).toBeNull();
  });

  it("allows ordinary names", () => {
    expect(isReservedName("acme-corp")).toBeNull();
    expect(isReservedName("Acme")).toBeNull();
  });
});
