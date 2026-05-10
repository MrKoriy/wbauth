# Phase 3 — Deferred Items

Issues discovered during Phase 3 execution that are out-of-scope for the
current plan and deferred. Per the executor `<scope_boundary>` rule:
auto-fixes apply only to issues directly caused by the current task's
changes. Pre-existing issues are logged here.

---

## DEF-03-01 — macOS UF_HIDDEN re-hide on `subprocess.run(["uv","run",...])`

**Discovered:** Plan 03-02 (Task 1, full-suite gate)
**Affected tests:** `python/tests/test_cli_keygen.py` (3 tests:
`test_keygen_creates_key_at_path`, `test_keygen_prints_kid_to_stdout`,
`test_keygen_errors_to_stderr_not_stdout`)
**Severity:** Low — only affects local `uv run pytest` runs on macOS;
CI runs on Ubuntu and is unaffected.

**Symptom:** When pytest spawns `subprocess.run(["uv", "run", "wbauth", ...])`,
the nested `uv` invocation triggers a venv re-sync which re-hides the
`_editable_impl_wbauth*.pth` files via macOS UF_HIDDEN, and the spawned
`wbauth` script then fails with `ModuleNotFoundError: No module named 'wbauth'`.

**Verified pre-existing:** `git stash && uv run pytest tests/test_cli_keygen.py`
on `8cf002e` (pre-Plan-03-02-Task-3 HEAD) reproduces 3/5 failures even with
no Plan 03-02 changes in the working tree. Cause is the macOS UF_HIDDEN +
Python 3.13 GH-99458 quirk documented in `scripts/post-sync.sh`, intersecting
with `uv run`'s on-the-fly sync behavior.

**Workaround for local runs:**
```bash
chflags nohidden .venv/lib/python3.13/site-packages/_editable_impl_wbauth*.pth
uv run pytest --no-header -q
```
(Already documented in macOS env reminder; the issue is the chflags wears off
during subprocess-driven re-sync.)

**Proper fix (out of scope):** Either rewrite `tests/test_cli_keygen.py` to
exercise `wbauth.cli.main` in-process (matches the pattern already used in
`tests/test_cli_inspect.py`, `tests/test_cli_register.py`, `tests/test_cli_serve.py`),
or upstream a fix to `uv` for macOS UF_HIDDEN preservation, or upgrade Python
past the GH-99458 fix window.

**Why not auto-fixed in Plan 03-02:** Plan 03-02 must_haves do not include
modifying `test_cli_keygen.py`; the file is from Phase 1. CI on Ubuntu does
not exhibit this flake (192/195 in-process tests pass cleanly; the 3
subprocess-spawned ones would also pass on Linux). The fix belongs in a
maintenance pass, not a feature plan.
