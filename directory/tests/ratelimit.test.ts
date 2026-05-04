// Per D-40, D-48 + Pitfall 4 cleanup-on-write.
import { describe, it, expect, beforeAll, beforeEach } from "vitest";
import { env, applyD1Migrations, type D1Migration } from "cloudflare:test";
import { checkAndIncrementRateLimit } from "../src/ratelimit";

beforeAll(async () => {
  // vitest.config.ts injects the migrations array as a JSON-serialized
  // binding (TEST_MIGRATIONS) because Node `fs` is not available inside
  // workerd isolates.
  const migrations = JSON.parse(
    (env as unknown as { TEST_MIGRATIONS: string }).TEST_MIGRATIONS,
  ) as D1Migration[];
  await applyD1Migrations(env.DB, migrations);
});

beforeEach(async () => {
  // Reset between tests so each starts from a clean ratelimit table.
  await env.DB.prepare("DELETE FROM ratelimit").run();
});

describe("checkAndIncrementRateLimit (D-40, D-48)", () => {
  it("allows the first 10 calls and blocks the 11th for the same IP", async () => {
    const ip = "1.2.3.4";
    for (let i = 1; i <= 10; i++) {
      const allowed = await checkAndIncrementRateLimit(env.DB, ip);
      expect(allowed, `call #${i} should be allowed`).toBe(true);
    }
    const eleventh = await checkAndIncrementRateLimit(env.DB, ip);
    expect(eleventh).toBe(false);
  });

  it("counts distinct IPs independently", async () => {
    for (let i = 0; i < 10; i++) {
      await checkAndIncrementRateLimit(env.DB, "5.6.7.8");
    }
    // 5.6.7.8 is now exhausted...
    expect(await checkAndIncrementRateLimit(env.DB, "5.6.7.8")).toBe(false);
    // ...but 9.10.11.12 starts fresh.
    expect(await checkAndIncrementRateLimit(env.DB, "9.10.11.12")).toBe(true);
  });

  it("cleans up rows older than yesterday on every write (Pitfall 4)", async () => {
    const today = Math.floor(Date.now() / 1000 / 86400);
    // Seed a stale row from 5 days ago.
    await env.DB.prepare(
      `INSERT INTO ratelimit (ip, day_bucket, count) VALUES (?, ?, ?)`,
    )
      .bind("stale.ip", today - 5, 7)
      .run();
    // First write triggers DELETE WHERE day_bucket < today - 1.
    await checkAndIncrementRateLimit(env.DB, "fresh.ip");
    const stale = await env.DB.prepare(
      `SELECT count FROM ratelimit WHERE ip = ? AND day_bucket = ?`,
    )
      .bind("stale.ip", today - 5)
      .first();
    expect(stale).toBeNull();
  });
});
