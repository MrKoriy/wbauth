"""Helpers for REDACTED repr/str on objects holding key material.

Greppable for security review: anywhere __repr__/__str__ touch keys, reuse this.
The literal string "REDACTED" appears in the produced repr so log scrapers can
flag it (and so test_repr_returns_REDACTED can assert on it).
"""
from __future__ import annotations


def redacted_repr(class_name: str, **public_fields: object) -> str:
    """Build a `<ClassName REDACTED key1='v1' key2='v2'>` style repr.

    Pass only NON-secret fields as kwargs. The output:
    - Always begins with `<{class_name} REDACTED ` so the literal token is
      detectable by log filters and unit tests.
    - Renders each public field via `!r` so quotes/escapes are explicit.
    """
    parts = " ".join(f"{k}={v!r}" for k, v in public_fields.items())
    return f"<{class_name} REDACTED {parts}>"
