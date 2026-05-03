"""Internal smoke tests for live conformance against external services.

Not part of the public API. Submodules are intended to be runnable as
``python -m wbauth._smoke.<name>`` from CI workflows. They exit non-zero on
any failure (so a CI step fails loudly).

Currently:

- ``cloudflare_debug``: signs a request via :class:`wbauth.Identity` (using
  the publicly-known RFC 9421 Appendix B.1.4 test key) and POSTs it to
  Cloudflare's ``crawltest.com/cdn-cgi/web-bot-auth`` debug verifier.
  Asserts HTTP 200. This is the Phase 1 hard exit criterion (IDENT-05).
"""
