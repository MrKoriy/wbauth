// Augment the global `Cloudflare.Env` interface that
// `@cloudflare/vitest-pool-workers/types` uses for the `env` re-export from
// "cloudflare:test". This lets test files reference `env.DB` and
// `env.DIRECTORY_PRIVATE_JWK` with the same types as the production worker.
declare global {
  namespace Cloudflare {
    interface Env {
      DB: D1Database;
      DIRECTORY_PRIVATE_JWK: string;
      // Injected by vitest.config.ts as a JSON-serialized array of
      // D1Migration entries, so test files can apply migrations without
      // touching node:fs from inside workerd.
      TEST_MIGRATIONS?: string;
    }
  }
}

export {};
