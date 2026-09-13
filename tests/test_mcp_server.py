from __future__ import annotations

import asyncio
import os
import sys

import pytest
from mcp import Client, StdioServerParameters
from starlette.testclient import TestClient

from ufora_cli import mcp_server


def test_mcp_disables_silent_background_auth_refresh():
    assert os.environ.get("D2L_NO_AUTO_LOGIN") == "1"


def test_loopback_host_detection():
    assert mcp_server._is_loopback_host("127.0.0.1")
    assert mcp_server._is_loopback_host("::1")
    assert mcp_server._is_loopback_host("localhost")
    assert not mcp_server._is_loopback_host("0.0.0.0")
    assert not mcp_server._is_loopback_host("192.168.1.20")
    assert not mcp_server._is_loopback_host("example.com")


def test_stdio_server_uses_stdio(monkeypatch: pytest.MonkeyPatch):
    calls = []
    monkeypatch.setattr(mcp_server.mcp, "run", lambda transport, **kwargs: calls.append((transport, kwargs)))

    mcp_server.run_server(transport="stdio")

    assert calls == [("stdio", {})]


def test_http_server_is_loopback_only(monkeypatch: pytest.MonkeyPatch):
    calls = []
    monkeypatch.setattr(mcp_server.mcp, "run", lambda transport, **kwargs: calls.append((transport, kwargs)))

    mcp_server.run_server(transport="http", host="127.0.0.1", port=9000, path="/mcp")
    assert calls == [
        (
            "streamable-http",
            {
                "host": "127.0.0.1",
                "port": 9000,
                "streamable_http_path": "/mcp",
                "json_response": True,
            },
        )
    ]

    with pytest.raises(ValueError, match="loopback"):
        mcp_server.run_server(transport="http", host="0.0.0.0")


def test_http_server_validates_transport_port_and_path():
    with pytest.raises(ValueError, match="transport"):
        mcp_server.run_server(transport="websocket")
    with pytest.raises(ValueError, match="port"):
        mcp_server.run_server(transport="http", port=0)
    with pytest.raises(ValueError, match="path"):
        mcp_server.run_server(transport="http", path="mcp")


def test_streamable_http_rejects_untrusted_browser_origin():
    app = mcp_server.mcp.streamable_http_app(
        host="127.0.0.1",
        streamable_http_path="/mcp",
        json_response=True,
    )
    with TestClient(app) as client:
        response = client.post(
            "/mcp",
            headers={
                "Host": "127.0.0.1:8765",
                "Origin": "https://attacker.example",
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )

    assert response.status_code == 403


def test_bundled_skill_is_available():
    text = mcp_server._skill_text()
    assert "# Ufora AI" in text
    assert "GR01" in text
    assert "Never run `d2l ...` commands" in text
    assert "search_course_content" in text
    assert "read_course_material" in text


def test_about_resource_has_safe_public_metadata():
    data = mcp_server.about()

    assert data["host"] == "https://ufora.ugent.be"
    assert data["access"] == "read-only"
    assert data["login_command"] == "ufora login"
    assert "token" not in str(data).lower()


def test_list_courses_query_searches_historical_offerings(monkeypatch: pytest.MonkeyPatch):
    data = [
        {"OrgUnit": {"Id": 1, "Name": "Logical Programming", "Code": "C003783A_2025"}},
        {"OrgUnit": {"Id": 2, "Name": "Information Security", "Code": "E019400B_2026"}},
    ]
    monkeypatch.setattr(mcp_server, "_call", lambda *args: data)

    result = mcp_server.list_courses(query="logical")

    assert [item["OrgUnit"]["Id"] for item in result] == [1]


def test_basic_mcp_wrappers_build_expected_read_commands(monkeypatch: pytest.MonkeyPatch):
    calls = []
    monkeypatch.setattr(mcp_server, "_call", lambda *args: calls.append(args) or {"args": args})

    assert mcp_server.doctor()["args"] == ("doctor",)
    assert mcp_server.whoami()["args"] == ("whoami",)
    assert mcp_server.list_courses(include_all=True)["args"] == ("courses", "--all")
    assert mcp_server.get_upcoming_due(7)["args"] == ("due", "--days", "7")
    assert mcp_server.get_calendar(10, "COURSE")["args"] == ("calendar", "--days", "10", "--course", "COURSE")
    assert mcp_server.get_course_content("COURSE", detailed=True)["args"] == ("content", "COURSE", "--toc")
    assert mcp_server.get_snapshot(course="COURSE", shallow=True, since_hours=24)["args"] == (
        "dump",
        "--course",
        "COURSE",
        "--shallow",
        "--since",
        "24",
    )
    assert len(calls) == 7


def test_mcp_parameter_validation_rejects_bad_ranges_and_empty_courses():
    with pytest.raises(ValueError, match="days"):
        mcp_server.get_upcoming_due(0)
    with pytest.raises(ValueError, match="days"):
        mcp_server.get_calendar(367)
    with pytest.raises(ValueError, match="course"):
        mcp_server.get_grades("   ")
    with pytest.raises(ValueError, match="since_hours"):
        mcp_server.get_snapshot(since_hours=0)


def _assert_course_understanding_tools(names: set[str]) -> None:
    assert "get_course_overview" in names
    assert "get_course_context" in names
    assert "search_course_content" in names
    assert "read_course_material" in names


def _assert_read_only_annotations(tools) -> None:
    assert tools
    for tool in tools:
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.destructive_hint is False


def test_mcp_exposes_course_understanding_tools():
    async def scenario():
        async with Client(mcp_server.mcp) as client:
            result = await client.list_tools()
            _assert_course_understanding_tools({tool.name for tool in result.tools})
            _assert_read_only_annotations(result.tools)

    asyncio.run(scenario())


def test_mcp_stdio_entrypoint_works_as_real_subprocess():
    async def scenario():
        server = StdioServerParameters(
            command=sys.executable,
            args=["-m", "ufora_cli.mcp_server"],
        )
        async with Client(server) as client:
            result = await client.list_tools()
            names = {tool.name for tool in result.tools}
            _assert_course_understanding_tools(names)
            _assert_read_only_annotations(result.tools)
            assert "doctor" in names
            assert "list_courses" in names

    asyncio.run(scenario())
