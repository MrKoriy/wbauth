// Worker bindings for the Phase 3 production directory.
// DB binds the wbauth-directory D1 database (D-34); DIRECTORY_PRIVATE_JWK is the
// JSON-stringified Ed25519 JWK that signs read-endpoint responses (D-42).
export type Env = {
  DB: D1Database;
  DIRECTORY_PRIVATE_JWK: string;
};
