# wbauth — Web Bot Auth for Python

Ed25519 [RFC 9421](https://www.rfc-editor.org/rfc/rfc9421) request signing with the IETF
Web Bot Auth profile, plus a pre-flight policy inspector (robots.txt, ai.txt,
llms.txt, signing directory). Python ≥ 3.11. TypeScript SDK: `npm install wb-auth`.

```bash
pip install wbauth                 # core: httpx + requests adapters, inspector, CLI
pip install "wbauth[playwright]"   # + Playwright adapter
pip install "wbauth[http2]"        # + HTTP/2 for a shared inspector client
```

From source:

```bash
uv sync --locked --all-extras --dev --all-packages
../scripts/post-sync.sh   # macOS-only; clears UF_HIDDEN flag on uv editable .pth
uv run pytest python/tests
```

## Why `scripts/post-sync.sh`?

On macOS, `uv` (≤0.11.7) sets the `UF_HIDDEN` file flag on the editable-install
marker file `.venv/lib/python*/site-packages/_editable_impl_wbauth.pth`. Python
3.13+ silently skips hidden `.pth` files per CPython security policy
(GH-99458 / issue #50028). Symptom: `import wbauth` fails with
`ModuleNotFoundError` even though `wbauth-*.dist-info/` is present in
site-packages. The post-sync script clears `UF_HIDDEN` via `chflags nohidden`.
No-op on Linux/Windows. Safe to re-run anytime.

See the [repository README](../README.md) for usage.
