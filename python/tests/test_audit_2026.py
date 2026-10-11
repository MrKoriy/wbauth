"""Regression suite for the Oct-2026 audit findings.

Each test pins one fixed defect (see CHANGELOG 0.3.0). Keep them green.
"""

from __future__ import annotations

import asyncio
import datetime
import importlib.metadata as md
import json
import warnings

import httpx
import pytest
from requests.structures import CaseInsensitiveDict

from wbauth import Identity, __version__
from wbauth.adapters import (
    RedirectNotSignedWarning,
    WebBotAuth,
    signed_async_client,
    signed_client,
)
from wbauth.adapters._utils import ensure_content_digest, host_matches
from wbauth.normalized_request import NormalizedRequest
from wbauth.policy import inspector as insp
from wbauth.policy.cache import PolicyCache, _parse_cache_control
from wbauth.policy.parsers.ai_txt import parse_ai_txt
from wbauth.policy.parsers.robots import DEFAULT_USER_AGENT, parse_robots
from wbauth.policy.policy import RobotsResult
from wbauth.policy.verdict import compute_verdict, restriction_applies
from wbauth.signer import MAX_EXPIRES_SECONDS, normalize_authority, sign

AGENT = "https://agent.example/.well-known/http-message-signatures-directory"
T0 = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)


@pytest.fixture
def ident():
    return Identity.from_test_key(AGENT)


@pytest.fixture(autouse=True)
def _fresh_cache():
    insp._reset_cache_for_tests()
    yield
    insp._reset_cache_for_tests()


def _verify(url: str, headers, ident: Identity) -> bool:
    from http_message_signatures import (
        HTTPMessageVerifier,
        HTTPSignatureKeyResolver,
        algorithms,
    )

    class R(HTTPSignatureKeyResolver):
        def resolve_public_key(self, key_id):
            return ident._active.private_key.public_key()

    req = NormalizedRequest(method="GET", url=url, headers=CaseInsensitiveDict(dict(headers)),
                            body=None)
    try:
        HTTPMessageVerifier(signature_algorithm=algorithms.ED25519, key_resolver=R()).verify(req)
    except Exception:  # noqa: BLE001
        return False
    return True


# ---------------------------------------------------------------- signer


def test_sign_roundtrip_verifies(ident):
    req = NormalizedRequest(method="GET", url="https://site.example/a?b=1", headers={}, body=None)
    sign(req, ident)
    assert _verify(req.url, req.headers, ident)


def test_resign_is_idempotent_no_duplicate_headers(ident):
    req = NormalizedRequest(method="GET", url="https://s.example/", headers={"signature": "old"},
                            body=None)
    sign(req, ident, created=T0, nonce="n1")
    sign(req, ident, created=T0, nonce="n2")
    assert sum(k.lower() == "signature" for k in req.headers) == 1
    assert 'nonce="n2"' in req.headers["Signature-Input"]


@pytest.mark.parametrize("bad", [0, -5, "60", None, True, False, MAX_EXPIRES_SECONDS + 1,
                                 10 * 365 * 86400, float("inf"), float("nan")])
def test_sign_rejects_bad_expiry(ident, bad):
    req = NormalizedRequest(method="GET", url="https://s.example/", headers={}, body=None)
    with pytest.raises(ValueError):
        sign(req, ident, expires_after_seconds=bad)


@pytest.mark.parametrize("method", ["DELETE", "QUERY", "post"])
def test_any_body_is_integrity_protected(ident, method):
    body = b'{"id":42}'
    headers: dict = {}
    ensure_content_digest(method, headers, body)
    req = NormalizedRequest(method=method, url="https://s.example/x", headers=headers, body=body)
    sign(req, ident)
    assert "content-digest" in req.headers["Signature-Input"]


@pytest.mark.parametrize("url,expected", [
    ("https://Example.COM/x", "example.com"),
    ("https://example.com:443/x", "example.com"),
    ("http://example.com:80/x", "example.com"),
    ("https://example.com:8443/x", "example.com:8443"),
    ("https://user:pw@example.com/x", "example.com"),
    ("https://[::1]:8443/", "[::1]:8443"),
])
def test_authority_is_rfc9421_normalized(url, expected):
    assert normalize_authority(url) == expected


def test_signature_with_default_port_verifies_against_host_header(ident):
    """Cloudflare derives @authority from Host (no :443) — we must match."""
    req = NormalizedRequest(method="GET", url="https://s.example:443/", headers={}, body=None)
    sign(req, ident)
    assert _verify("https://s.example/", req.headers, ident)


def test_label_and_nonce_validation(ident):
    req = NormalizedRequest(method="GET", url="https://s.example/", headers={}, body=None)
    with pytest.raises(ValueError):
        sign(req, ident, label="Bad Label")
    with pytest.raises(ValueError):
        sign(req, ident, nonce="caf\u00e9")


# ---------------------------------------------------------------- redirects


def _redirect_handler(seen: list):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((str(request.url), dict(request.headers)))
        if request.url.host == "a.example":
            return httpx.Response(302, headers={"location": "https://b.example/next"})
        return httpx.Response(200)
    return handler


def test_signed_client_resigns_every_redirect_hop(ident):
    seen: list = []
    with signed_client(ident, transport=httpx.MockTransport(_redirect_handler(seen)),
                       follow_redirects=True) as c:
        assert c.get("https://a.example/").status_code == 200
    assert [u for u, _ in seen] == ["https://a.example/", "https://b.example/next"]
    for url, headers in seen:
        assert _verify(url, headers, ident), url


def test_signed_async_client_resigns_every_redirect_hop(ident):
    seen: list = []

    async def go():
        async with signed_async_client(
            ident, transport=httpx.MockTransport(_redirect_handler(seen)), follow_redirects=True
        ) as c:
            return await c.get("https://a.example/")

    assert asyncio.run(go()).status_code == 200
    for url, headers in seen:
        assert _verify(url, headers, ident), url


def test_signed_client_signs_post_body(ident):
    seen: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    with signed_client(ident, transport=httpx.MockTransport(handler)) as c:
        c.post("https://s.example/", content=b"abc")
    assert seen[0].headers["content-digest"].startswith("sha-256=:")
    assert "content-digest" in seen[0].headers["signature-input"]


def test_webbotauth_warns_when_redirect_could_not_be_resigned(ident):
    seen: list = []
    with httpx.Client(transport=httpx.MockTransport(_redirect_handler(seen)),
                      auth=WebBotAuth(ident), follow_redirects=True) as c, \
            pytest.warns(RedirectNotSignedWarning):
        c.get("https://a.example/")


def test_webbotauth_no_warning_without_redirects(ident):
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200)),
                      auth=WebBotAuth(ident)) as c, warnings.catch_warnings():
        warnings.simplefilter("error")
        c.get("https://a.example/")


def test_identity_repr_never_leaks_private_key(ident):
    import base64

    from cryptography.hazmat.primitives import serialization
    raw = ident._active.private_key.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
        serialization.NoEncryption())
    assert base64.urlsafe_b64encode(raw).rstrip(b"=").decode() not in repr(ident)


# ---------------------------------------------------------------- packaging


def test_distribution_metadata_matches_version():
    assert md.version("wbauth-sdk") == __version__


def test_default_user_agent_tracks_version():
    assert DEFAULT_USER_AGENT == f"wbauth/{__version__}"


# ---------------------------------------------------------------- inspector


def _mock_site(robots: str = "User-agent: *\nAllow: /\n", counter: list | None = None,
               status: dict | None = None, extra: dict | None = None):
    status = status or {}
    extra = extra or {}

    async def handler(request: httpx.Request) -> httpx.Response:
        if counter is not None:
            counter.append(request)
        await asyncio.sleep(0)  # let concurrent callers overlap
        p = request.url.path
        if p in status:
            return httpx.Response(status[p])
        if p in extra:
            return extra[p](request)
        if p == "/robots.txt":
            return httpx.Response(200, text=robots, headers={"content-type": "text/plain"})
        return httpx.Response(404)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_inspect_allowed_happy_path():
    async def go():
        async with _mock_site() as c:
            return await insp.inspect("https://s.example/a", client=c)
    p = asyncio.run(go())
    assert p.verdict == "allowed" and not p.partial


def test_inspect_robots_disallow_is_path_scoped():
    async def go():
        async with _mock_site("User-agent: *\nDisallow: /private\n") as c:
            return (await insp.inspect("https://s.example/private/x", client=c),
                    await insp.inspect("https://s.example/public", client=c))
    priv, pub = asyncio.run(go())
    assert priv.verdict == "forbidden" and pub.verdict == "allowed"


@pytest.mark.parametrize("code,verdict", [(503, "forbidden"), (429, "forbidden"),
                                          (404, "allowed"), (401, "allowed")])
def test_robots_status_mapping(code, verdict):
    async def go():
        async with _mock_site(status={"/robots.txt": code}) as c:
            return (await insp.inspect("https://s.example/", client=c)).verdict
    assert asyncio.run(go()) == verdict


def test_robots_full_user_agent_string_matches_product_token():
    robots = "User-agent: ExampleAgent\nDisallow: /\n\nUser-agent: *\nAllow: /\n"
    r = parse_robots(robots, "text/plain", "https://s.example/x",
                     "ExampleAgent/1.0 (+https://agent.example)")
    assert r.can_fetch_url is False


def test_robots_bom_is_tolerated_end_to_end():
    def robots(_r):
        return httpx.Response(200, content=b"\xef\xbb\xbfUser-agent: *\nDisallow: /\n",
                              headers={"content-type": "text/plain"})

    async def go():
        async with _mock_site(extra={"/robots.txt": robots}) as c:
            return await insp.inspect("https://s.example/x", client=c)
    assert asyncio.run(go()).verdict == "forbidden"


def test_second_inspect_hits_cache():
    calls: list = []

    async def go():
        async with _mock_site(counter=calls) as c:
            await insp.inspect("https://s.example/a", client=c)
            await insp.inspect("https://s.example/b", client=c)
    asyncio.run(go())
    assert len(calls) == 4


def test_concurrent_inspect_is_deduplicated():
    calls: list = []

    async def go():
        async with _mock_site(counter=calls) as c:
            return await asyncio.gather(
                *[insp.inspect(f"https://s.example/{i}", client=c) for i in range(10)])
    results = asyncio.run(go())
    assert len(calls) == 4, f"{len(calls)} requests for 10 concurrent calls"
    assert {p.verdict for p in results} == {"allowed"}


def test_http_url_fetches_http_origin():
    assert insp._endpoints(insp._origin_host("http://s.example:8080/"))["robots"] == \
        "http://s.example:8080/robots.txt"
    assert insp._endpoints(insp._origin_host("http://s.example:80/"))["robots"] == \
        "http://s.example/robots.txt"
    assert insp._endpoints(insp._origin_host("https://s.example:443/"))["robots"] == \
        "https://s.example/robots.txt"


def test_http_and_https_do_not_share_cache():
    calls: list = []

    async def go():
        async with _mock_site(counter=calls) as c:
            await insp.inspect("https://s.example/", client=c)
            await insp.inspect("http://s.example/", client=c)
    asyncio.run(go())
    assert {r.url.scheme for r in calls} == {"http", "https"}
    assert len(calls) == 8


@pytest.mark.parametrize("target", [
    "http://169.254.169.254/latest/meta-data", "http://127.0.0.1/", "http://localhost/",
    "http://[::1]/", "http://10.0.0.5/", "http://2130706433/", "file:///etc/passwd",
    "http://[::ffff:127.0.0.1]/",
])
def test_inspector_refuses_redirect_to_internal_address(target):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "s.example":
            return httpx.Response(301, headers={"location": target})
        return httpx.Response(200, text="User-agent: *\nAllow: /\n")

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await insp.inspect("https://s.example/", client=c)
    p = asyncio.run(go())
    assert p.robots is None
    assert "robots" in p.errors and p.verdict != "allowed"


def test_inspector_allows_public_cross_host_redirect():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "s.example" and request.url.path == "/robots.txt":
            return httpx.Response(301, headers={"location": "https://cdn.example/robots.txt"})
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /\n")
        return httpx.Response(404)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await insp.inspect("https://s.example/x", client=c)
    assert asyncio.run(go()).verdict == "forbidden"


def test_inspector_local_origin_may_redirect_locally():
    """Inspecting a local dev server is explicit — local→local is fine."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt" and request.url.port == 8000:
            return httpx.Response(302, headers={"location": "http://127.0.0.1:8001/robots.txt"})
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        return httpx.Response(404)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await insp.inspect("http://127.0.0.1:8000/", client=c)
    assert asyncio.run(go()).verdict == "allowed"


def test_redirect_limit_is_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        n = int(request.url.params.get("n", "0"))
        if request.url.path == "/robots.txt":
            return httpx.Response(302, headers={"location": f"/robots.txt?n={n + 1}"})
        return httpx.Response(404)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await insp.inspect("https://s.example/", client=c)
    p = asyncio.run(go())
    assert isinstance(p.errors["robots"], httpx.TooManyRedirects)
    assert p.verdict == "allowed"


# ---------------------------------------------------------------- ai.txt


def _robots_ok() -> RobotsResult:
    return RobotsResult(can_fetch_url=True, sitemaps=[], raw="", user_agent_evaluated="Bot")


@pytest.mark.parametrize("path,verdict", [("/blog/1", "allowed"), ("/admin/x", "restricted"),
                                          ("/admin", "allowed")])
def test_ai_txt_restriction_is_path_scoped(path, verdict):
    ai = parse_ai_txt("[restrictions]\n- /admin/ not for training\n")
    assert compute_verdict(_robots_ok(), ai, None, None, {}, False, target_path=path)[0] == verdict


def test_ai_txt_restriction_without_path_is_site_wide():
    ai = parse_ai_txt("[restrictions]\n- No AI/ML training on any content\n")
    assert compute_verdict(_robots_ok(), ai, None, None, {}, False, target_path="/x")[0] == \
        "restricted"


@pytest.mark.parametrize("rule,path,applies", [
    ("see https://example.com/terms", "/x", True),  # URL is not a path scope
    ("/api/* is off limits", "/api/v1", True),
    ("/api/* is off limits", "/apis", False),
    ("no training on /docs or /blog.", "/blog/post", True),
    ("no training on /docs or /blog.", "/shop", False),
])
def test_restriction_applies(rule, path, applies):
    assert restriction_applies(rule, path) is applies


def test_ai_txt_tolerates_comments_casing_and_bom():
    r = parse_ai_txt("\ufeff# hi\n[RESTRICTIONS]\n- no training # why\n\n[Permissions]\n- index\n")
    assert r.restrictions == ["no training"] and r.permissions == ["index"]


def test_ai_txt_alternative_bullets():
    r = parse_ai_txt("[restrictions]\n* no training\n-no resale\n+ no ads\n\u2022 no x\n-\n")
    assert r.restrictions == ["no training", "no resale", "no ads", "no x"]


# ---------------------------------------------------------------- cache


@pytest.mark.parametrize("hdr,expected", [
    (None, (True, None)), ("max-age=60", (True, 60)), ("no-store", (False, None)),
    ("public, max-age=0", (True, 0)), ('max-age="30"', (True, 30)),
    ("private, max-age=60", (True, 60)),
])
def test_cache_control_parsing(hdr, expected):
    assert _parse_cache_control(hdr) == expected


def test_cache_ttl_expiry():
    now = [0.0]
    c = PolicyCache(timer=lambda: now[0])
    c.set("s.example", "signing_directory", "v")
    assert c.get("S.EXAMPLE:443", "signing_directory") is not None
    now[0] = 301
    assert c.get("s.example", "signing_directory") is None


def test_etag_revalidation_uses_304(monkeypatch):
    calls: list = []

    def robots(request: httpx.Request) -> httpx.Response:
        if request.headers.get("if-none-match") == '"v1"':
            return httpx.Response(304, headers={"etag": '"v1"'})
        return httpx.Response(200, text="User-agent: *\nDisallow: /secret\n",
                              headers={"content-type": "text/plain", "etag": '"v1"',
                                       "cache-control": "max-age=1"})

    now = [1000.0]
    monkeypatch.setattr(insp, "_CACHE", PolicyCache(timer=lambda: now[0]))

    async def go():
        async with _mock_site(counter=calls, extra={"/robots.txt": robots}) as c:
            first = await insp.inspect("https://s.example/secret", client=c)
            now[0] += 5  # expire
            second = await insp.inspect("https://s.example/secret", client=c)
            return first, second
    first, second = asyncio.run(go())
    robots_calls = [r for r in calls if r.url.path == "/robots.txt"]
    assert len(robots_calls) == 2
    assert robots_calls[1].headers["if-none-match"] == '"v1"'
    assert first.verdict == second.verdict == "forbidden"


def test_no_store_is_never_revalidated():
    c = PolicyCache()
    c.set("s.example", "robots", "v", cache_control="no-store", etag='"x"')
    assert c.get_stale("s.example", "robots") is None


def test_cache_persistence_roundtrip(tmp_path):
    async def go():
        async with _mock_site("User-agent: *\nDisallow: /p\n") as c:
            await insp.inspect("https://s.example/", client=c)
    asyncio.run(go())
    path = tmp_path / "cache.json"
    assert insp.save_cache(path) == 4
    assert "PRIVATE" not in path.read_text()
    insp._reset_cache_for_tests()
    assert insp.load_cache(path) == 4

    def boom(_r):  # any network call now is a test failure
        raise AssertionError("network used despite persisted cache")

    async def again():
        async with httpx.AsyncClient(transport=httpx.MockTransport(boom)) as c:
            return await insp.inspect("https://s.example/p/1", client=c)
    assert asyncio.run(again()).verdict == "forbidden"


def test_load_cache_tolerates_garbage(tmp_path):
    p = tmp_path / "c.json"
    p.write_text("{not json")
    assert insp.load_cache(p) == 0
    p.write_text(json.dumps({"version": 1, "entries": [{"host": "x"}, 5]}))
    assert insp.load_cache(p) == 0
    assert insp.load_cache(tmp_path / "missing.json") == 0


# ---------------------------------------------------------------- utils


@pytest.mark.parametrize("host,allow,ok", [
    ("a.example.com", ["*.example.com"], True),
    ("example.com", ["*.example.com"], True),
    ("evilexample.com", ["*.example.com"], False),
    ("EXAMPLE.com.", ["example.com"], True),
    ("example.com.evil", ["example.com"], False),
])
def test_host_matches(host, allow, ok):
    assert host_matches(host, allow) is ok


def test_content_digest_rejects_str_body():
    with pytest.raises(TypeError):
        ensure_content_digest("POST", {}, "text")  # type: ignore[arg-type]
