"""Smoke test for the adapters package skeleton (Plan 02-01 Task 1).

Verifies the public surface and dependency set required for Phase 2:
- `wbauth.adapters` re-exports the three public symbols.
- `wbauth` (top level) re-exports the same three symbols.
- The Phase-2 runtime + dev deps import cleanly.
"""
from __future__ import annotations


def test_adapters_subpackage_reexports():
    """`from wbauth.adapters import ...` resolves the three public symbols."""
    from wbauth.adapters import WebBotAuth, WebBotAuthAdapter, attach_signing
    assert WebBotAuth is not None
    assert WebBotAuthAdapter is not None
    assert attach_signing is not None


def test_top_level_reexports():
    """`from wbauth import ...` exposes the adapter trio at package root."""
    from wbauth import WebBotAuth, WebBotAuthAdapter, attach_signing
    assert WebBotAuth is not None
    assert WebBotAuthAdapter is not None
    assert attach_signing is not None


def test_phase2_runtime_deps_importable():
    """Phase-2 runtime deps install cleanly via uv sync."""
    import cachetools
    import playwright
    import protego
    import requests
    # Versions must be in the pinned ranges:
    assert int(requests.__version__.split(".")[0]) == 2
    assert int(cachetools.__version__.split(".")[0]) >= 4  # min any cachetools 4+
    assert protego is not None
    assert playwright is not None


def test_phase2_dev_deps_importable():
    """Phase-2 dev deps install cleanly via `uv sync --group dev`."""
    import pytest_httpx
    import responses
    assert pytest_httpx is not None
    assert responses is not None
