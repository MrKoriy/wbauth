"""Signing-directory parser (draft-meunier-http-message-signatures-directory-05).

Lightweight — surfaces presence + key count + content-type-correctness
only. NO JWK validation (verifier's job, not inspector's).

Pitfall 3: presence of the directory does NOT mean signing is *required*;
it means the origin advertises which keys it accepts. The verdict engine
treats presence as advisory ("signing supported (optional)") and never
escalates to ``restricted`` on this signal alone.
"""
from __future__ import annotations

import json

from ..policy import SigningDirectoryResult

_SPEC_CONTENT_TYPE = "application/http-message-signatures-directory+json"


def parse_signing_directory(
    text: str, content_type: str | None
) -> SigningDirectoryResult:
    """Parse the signing-directory JSON body; never raises.

    Malformed JSON is treated as "absent" rather than raising — the verdict
    engine doesn't care WHY parsing failed, just that it can't.
    """
    ct_correct = bool(content_type) and content_type.startswith(_SPEC_CONTENT_TYPE)
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return SigningDirectoryResult(
            present=False,
            keys=[],
            content_type_correct=False,
            raw=text,
        )
    keys = data.get("keys", []) if isinstance(data, dict) else []
    keys_list = list(keys) if isinstance(keys, list) else []
    return SigningDirectoryResult(
        present=bool(keys_list),
        keys=keys_list,
        content_type_correct=ct_correct,
        raw=text,
    )
