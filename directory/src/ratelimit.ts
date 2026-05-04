// Per D-40, D-48: 10 register attempts per IP per day, enforced via D1 small-row
// strategy. Each call atomically (a) sweeps stale rows older than yesterday
// (Pitfall 4 cleanup-on-write), (b) UPSERTs the (ip, day_bucket) row with
// count+1, and (c) reads back the post-increment count. The whole sequence
// runs in a single .batch([...]) round-trip per Pattern 4.

const PER_IP_PER_DAY = 10;

export async function checkAndIncrementRateLimit(
  db: D1Database,
  ip: string,
): Promise<boolean> {
  const dayBucket = Math.floor(Date.now() / 1000 / 86400);
  const [, , countRow] = await db.batch([
    db.prepare(`DELETE FROM ratelimit WHERE day_bucket < ?`).bind(dayBucket - 1),
    db
      .prepare(
        `INSERT INTO ratelimit (ip, day_bucket, count) VALUES (?1, ?2, 1)
         ON CONFLICT(ip, day_bucket) DO UPDATE SET count = count + 1`,
      )
      .bind(ip, dayBucket),
    db
      .prepare(`SELECT count FROM ratelimit WHERE ip = ? AND day_bucket = ?`)
      .bind(ip, dayBucket),
  ]);
  const count =
    (countRow.results?.[0] as { count: number } | undefined)?.count ?? 0;
  return count <= PER_IP_PER_DAY;
}
