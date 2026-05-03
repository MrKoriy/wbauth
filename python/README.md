# wbauth (Python)

```bash
pip install wbauth   # Phase 5 — not yet published

# From source (Phase 1):
uv sync --all-extras --dev --all-packages
../scripts/post-sync.sh   # macOS-only; clears UF_HIDDEN flag on uv editable .pth
uv run wbauth keygen
```

## Why `scripts/post-sync.sh`?

On macOS, `uv` (≤0.11.7) sets the `UF_HIDDEN` file flag on the editable-install
marker file `.venv/lib/python*/site-packages/_editable_impl_wbauth.pth`. Python
3.13+ silently skips hidden `.pth` files per CPython security policy
(GH-99458 / issue #50028). Symptom: `import wbauth` fails with
`ModuleNotFoundError` even though `wbauth-0.1.0.dist-info/` is present in
site-packages. The post-sync script clears `UF_HIDDEN` via `chflags nohidden`.
No-op on Linux/Windows. Safe to re-run anytime.

See repo root README for the full project description.
