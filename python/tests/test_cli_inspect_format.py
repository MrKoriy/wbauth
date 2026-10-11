"""`wbauth inspect --format table` and `--cache`."""

from __future__ import annotations

import datetime
import json
from unittest.mock import patch

import httpx

from wbauth.cli import main
from wbauth.policy import SitePolicy
from wbauth.policy.policy import AiTxtResult, RobotsResult


def _policy() -> SitePolicy:
    req = httpx.Request("GET", "https://e.example/llms.txt")
    return SitePolicy(
        url="https://e.example/x",
        robots=RobotsResult(can_fetch_url=False, sitemaps=[], raw="", user_agent_evaluated="B",
                            crawl_delay=2.0),
        ai_txt=AiTxtResult(identity={}, permissions=["index"], restrictions=["no training"]),
        llms_txt=None,
        signing_directory=None,
        verdict="forbidden",
        reasons=["robots.txt disallows our user-agent for this path"],
        partial=False,
        errors={
            "llms_txt": httpx.HTTPStatusError("404", request=req,
                                              response=httpx.Response(404, request=req)),
            "signing_directory": httpx.ConnectError("boom"),
        },
        fetched_at=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
    )


def test_table_format(capsys):
    with patch("wbauth.cli.inspect", return_value=_policy()):
        rc = main(["inspect", "https://e.example/x", "--format", "table"])
    out = capsys.readouterr().out
    assert rc == 2
    assert out.startswith("FORBIDDEN  https://e.example/x")
    assert "\033[" not in out  # not a TTY → no ANSI colors
    assert "DISALLOWS this path, crawl-delay 2s" in out
    assert "1 restriction(s), 1 permission(s)" in out
    assert "absent" in out and "HTTP 404" in out
    assert "ConnectError: boom" in out


def test_format_json_equals_legacy_flag(capsys):
    with patch("wbauth.cli.inspect", return_value=_policy()):
        main(["inspect", "https://e.example/x", "--format", "json"])
        a = json.loads(capsys.readouterr().out)
        main(["inspect", "https://e.example/x", "--json"])
        b = json.loads(capsys.readouterr().out)
    assert a == b and a["verdict"] == "forbidden"


def test_cache_flag_loads_and_saves(tmp_path, capsys):
    path = tmp_path / "sub" / "cache.json"
    with patch("wbauth.cli.inspect", return_value=_policy()), \
            patch("wbauth.policy.load_cache") as load, patch("wbauth.policy.save_cache") as save:
        main(["inspect", "https://e.example/x", "--cache", str(path)])
    load.assert_called_once_with(str(path))
    save.assert_called_once_with(str(path))
