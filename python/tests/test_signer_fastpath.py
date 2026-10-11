"""Differential test: wbauth's direct RFC 9421 base == http-message-signatures.

For URLs whose authority is already normalized (no userinfo, no default
port) the fast path must be byte-identical to the reference library.
"""

from __future__ import annotations

import datetime

from hypothesis import given, settings
from hypothesis import strategies as st
from http_message_signatures import HTTPMessageSigner, HTTPSignatureKeyResolver, algorithms

from wbauth import Identity
from wbauth.adapters._utils import ensure_content_digest
from wbauth.normalized_request import NormalizedRequest
from wbauth.signer import WEB_BOT_AUTH_TAG, sign

IDENT = Identity.from_test_key("https://agent.example/dir")

hosts = st.from_regex(r"[a-z][a-z0-9-]{0,20}(\.[a-z]{2,6}){1,2}", fullmatch=True)
ports = st.one_of(st.none(), st.integers(1024, 65535))
paths = st.from_regex(r"(/[A-Za-z0-9._~-]{0,10}){0,4}(\?[a-z]=[0-9]{1,3})?", fullmatch=True)
nonces = st.from_regex(r"[A-Za-z0-9_-]{1,64}", fullmatch=True)
bodies = st.one_of(st.none(), st.binary(min_size=1, max_size=256))
methods = st.sampled_from(["GET", "POST", "PUT", "PATCH", "DELETE"])
labels = st.from_regex(r"[a-z][a-z0-9_-]{0,8}", fullmatch=True)
created = st.integers(1_600_000_000, 2_200_000_000)
expires = st.integers(1, 3600)


class _R(HTTPSignatureKeyResolver):
    def resolve_private_key(self, key_id):
        return IDENT._active.private_key


@settings(max_examples=300, deadline=None)
@given(hosts, ports, paths, nonces, bodies, methods, labels, created, expires)
def test_fast_path_matches_reference(host, port, path, nonce, body, method, label, ts, exp):
    url = f"https://{host}{':' + str(port) if port else ''}{path or '/'}"
    headers: dict = {}
    if body:
        ensure_content_digest(method, headers, body)
    when = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)
    ours = NormalizedRequest(method=method, url=url, headers=dict(headers), body=body)
    sig = sign(ours, IDENT, created=when, expires_after_seconds=exp, nonce=nonce, label=label)

    ref = NormalizedRequest(method=method, url=url,
                            headers={**headers, "Signature-Agent": sig.signature_agent}, body=body)
    covered = ["@authority", "signature-agent"] + (["content-digest"] if body else [])
    HTTPMessageSigner(signature_algorithm=algorithms.ED25519, key_resolver=_R()).sign(
        ref, key_id=IDENT.kid, created=when,
        expires=when + datetime.timedelta(seconds=exp), nonce=nonce, label=label,
        tag=WEB_BOT_AUTH_TAG, covered_component_ids=covered,
    )
    assert sig.signature_input == ref.headers["Signature-Input"]
    assert sig.signature == ref.headers["Signature"]
