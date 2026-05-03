"""Pytest fixtures for the wbauth test suite.

The ``vector`` fixture parametrizes over every directory under
``spec/test-vectors/`` that has an ``input.json`` (so the live-check
directory ``06-cloudflare-debug-live/`` is automatically excluded — it has
only a README, no byte-equality oracle).
"""
import json
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
VECTORS_DIR = REPO_ROOT / "spec" / "test-vectors"


def all_vector_dirs() -> list[pathlib.Path]:
    return sorted(
        p for p in VECTORS_DIR.iterdir()
        if p.is_dir() and (p / "input.json").exists()
    )


@pytest.fixture(params=all_vector_dirs(), ids=lambda p: p.name)
def vector(request) -> dict:
    d = request.param
    return {
        "name": d.name,
        "input": json.loads((d / "input.json").read_text()),
        "expected": json.loads((d / "expected.json").read_text()),
    }
