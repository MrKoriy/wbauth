"""OpenAI Agents SDK x wbauth demo (DIST-06).

What this demonstrates:
- WebBotAuth(identity) + httpx.Client used inside an OpenAI Agents SDK
  @function_tool. The Agent's tool makes signed HTTP requests to a
  third-party URL. (We do NOT sign requests TO openai.com — only the
  outbound requests the Agent's tools make.)
- Real-mode (with OPENAI_API_KEY): runs Runner.run() with a real Agent
  that decides to call the tool against a benign URL.
- Mock-mode (no OPENAI_API_KEY): skips the Agent + Runner entirely and
  calls signed_get directly against our directory Worker
  (https://wbauth.silov801.workers.dev/agents). Prints a result dict
  with `signature_input_present: True` — the verification anchor that
  proves a signed Signature-Input header was emitted to stdout.

Run:
    uv pip install "openai-agents" "httpx>=0.28,<1"

    # Mock mode (no key required, no openai-agents needed):
    python examples/openai_agents_demo.py

    # Real mode (LLM key drives the Agent):
    OPENAI_API_KEY=sk-... python examples/openai_agents_demo.py

Pitfalls:
- Tool returns a string summary, not raw HTTP. Agents SDK tools must
  return JSON-serializable types; string is the safest.
- Mock-mode bypasses Runner.run entirely — directly invokes signed_get.
  This means `agents` (openai-agents pip package) is only imported in
  real_mode, so mock-mode runs even without that dep installed.

Per CONTEXT D-70: this demo does NOT depend on Cloudflare verifier
round-trip. The verification anchor is `signature_input_present: True`
in the printed dict — proof that the SDK successfully emitted a signed
Signature-Input header.

Per CONTEXT D-71: upstream PRs to mcp-agent / openai-agents-python
examples (DIST-07) are NOT in this plan — they are scheduled for Phase 5.
"""
import asyncio
import os
from pathlib import Path

import httpx

from wbauth import Identity, WebBotAuth

WORKER_URL = "https://wbauth.silov801.workers.dev/agents"
KEY_PATH = Path("~/.config/wbauth/key.pem").expanduser()


def make_identity() -> Identity:
    """Two-load pattern: derive the kid from the on-disk key, then re-load
    with the canonical signature_agent_url that includes that kid."""
    placeholder = Identity.load_or_generate(
        KEY_PATH,
        signature_agent_url="https://example.invalid/placeholder",
    )
    return Identity.load_or_generate(
        KEY_PATH,
        signature_agent_url=(
            "https://wbauth.silov801.workers.dev/.well-known/"
            f"http-message-signatures-directory/{placeholder.kid}"
        ),
    )


def signed_get(url: str, identity: Identity) -> dict:
    """Single signed GET request via httpx + WebBotAuth.

    Returns a dict with the URL, HTTP status, our identity's kid, and
    `signature_input_present` — True iff the actual sent request
    (resp.request.headers, post-auth-flow) carried a Signature-Input
    header. The latter is the verification anchor for mock-mode.
    """
    with httpx.Client(auth=WebBotAuth(identity)) as client:
        resp = client.get(url, follow_redirects=True)
        # Case-insensitive header lookup over the actual sent headers.
        sig_input_present = "signature-input" in {
            k.lower() for k in resp.request.headers
        }
        return {
            "url": url,
            "status": resp.status_code,
            "kid": identity.kid,
            "signature_input_present": sig_input_present,
        }


async def real_mode(identity: Identity) -> None:
    """Run a real OpenAI Agent with a signed-fetch tool. Requires
    OPENAI_API_KEY and the `openai-agents` pip package."""
    from agents import Agent, Runner, function_tool

    @function_tool
    def fetch_page(url: str) -> str:
        """Fetch a URL with a signed Web Bot Auth request and return a summary."""
        result = signed_get(url, identity)
        return (
            f"GET {url} -> HTTP {result['status']} "
            f"(signed with kid={result['kid']})"
        )

    agent = Agent(
        name="WebBotAuthDemo",
        instructions=(
            "You demonstrate Web Bot Auth signed requests. When asked to "
            "fetch a URL, use the fetch_page tool. Always report the HTTP status."
        ),
        tools=[fetch_page],
    )
    result = await Runner.run(
        agent,
        "Fetch https://example.com and tell me the status.",
    )
    print(f"[agent] {result.final_output}")


def mock_mode(identity: Identity) -> None:
    """No LLM, no Agent — just call signed_get directly so we prove the
    SDK API surface (httpx + WebBotAuth) actually emits a signed
    Signature-Input header to stdout."""
    print("[demo] Calling signed_get directly (no LLM).")
    result = signed_get(WORKER_URL, identity)
    print(f"[demo] {result}")


def main() -> None:
    identity = make_identity()
    if os.getenv("OPENAI_API_KEY"):
        print("[demo] Real mode (OpenAI key detected)")
        asyncio.run(real_mode(identity))
    else:
        print("[demo] Mock mode (no OpenAI key)")
        mock_mode(identity)


if __name__ == "__main__":
    main()
