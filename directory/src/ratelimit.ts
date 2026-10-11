// Per D-40, D-48: D1 small-row rate limiting, cleanup-on-write (Pitfall 4).
//
// 2026-10 audit:
//  - `scope` gives /register/challenge and /register/submit separate daily
//    budgets — previously one registration spent 2 of the 10 shared calls.
//  - IPv6 clients are bucketed by /64: a single host usually owns a whole
//    /64, so per-address limits were trivially bypassed.
export const PER_IP_PER_DAY = 10;

function expandIPv6(ip: string): string[] | null {
  let addr = ip.toLowerCase();
  const zone = addr.indexOf("%");
  if (zone >= 0) addr = addr.slice(0, zone);
  // Embedded IPv4 tail (::ffff:1.2.3.4).
  const v4 = addr.match(/(\d+)\.(\d+)\.(\d+)\.(\d+)$/);
  if (v4) {
    const [a, b, c, d] = v4.slice(1).map(Number) as [number, number, number, number];
    const tail = `${((a << 8) | b).toString(16)}:${((c << 8) | d).toString(16)}`;
    addr = addr.slice(0, addr.length - v4[0].length) + tail;
  }
  const halves = addr.split("::");
  if (halves.length > 2) return null;
  const head = halves[0] ? halves[0].split(":") : [];
  const tail = halves.length === 2 && halves[1] ? halves[1].split(":") : [];
  const fill = halves.length === 2 ? 8 - head.length - tail.length : 0;
  if (fill < 0) return null;
  const groups = [...head, ...Array(fill).fill("0"), ...tail];
  if (groups.length !== 8 || groups.some((g) => !/^[0-9a-f]{1,4}$/.test(g))) {
    return null;
  }
  return groups.map((g) => g.padStart(4, "0"));
}

/** Rate-limit key for an address: IPv4 as-is, IPv6 collapsed to its /64. */
export function ipBucket(ip: string): string {
  if (!ip.includes(":")) return ip;
  const g = expandIPv6(ip);
  if (!g) return ip;
  // IPv4-mapped (::ffff:a.b.c.d) → treat as the IPv4 address.
  if (g.slice(0, 5).every((x) => x === "0000") && g[5] === "ffff") {
    const n = (h: string) => [Number.parseInt(h.slice(0, 2), 16), Number.parseInt(h.slice(2), 16)];
    return [...n(g[6] as string), ...n(g[7] as string)].join(".");
  }
  return `${g.slice(0, 4).join(":")}::/64`;
}

export async function checkAndIncrementRateLimit(
  db: D1Database,
  ip: string,
  scope = "register",
  limit = PER_IP_PER_DAY,
): Promise<boolean> {
  const dayBucket = Math.floor(Date.now() / 1000 / 86400);
  const key = `${scope}:${ipBucket(ip)}`;
  const [, , countRow] = await db.batch([
    db.prepare(`DELETE FROM ratelimit WHERE day_bucket < ?`).bind(dayBucket - 1),
    db
      .prepare(
        `INSERT INTO ratelimit (ip, day_bucket, count) VALUES (?1, ?2, 1)
         ON CONFLICT(ip, day_bucket) DO UPDATE SET count = count + 1`,
      )
      .bind(key, dayBucket),
    db
      .prepare(`SELECT count FROM ratelimit WHERE ip = ? AND day_bucket = ?`)
      .bind(key, dayBucket),
  ]);
  const count =
    (countRow.results?.[0] as { count: number } | undefined)?.count ?? 0;
  return count <= limit;
}
