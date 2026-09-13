from __future__ import annotations

import asyncio

from mcp import Client
import pytest

from ufora_cli import mcp_server


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


def test_http_server_validates_port_and_path():
    with pytest.raises(ValueError, match="port"):
        mcp_server.run_server(transport="http", port=0)
    with pytest.raises(ValueError, match="path"):
        mcp_server.run_server(transport="http", path="mcp")


def test_bundled_skill_is_available():
    text = mcp_server._skill_text()
    assert "# Ufora AI" in text
    assert "GR01" in text
    assert "Never run `d2l ...` commands" in text
    assert "search_course_content" in text
    assert "read_course_material" in text


def test_list_courses_query_searches_historical_offerings(monkeypatch: pytest.MonkeyPatch):
    data = [
        {"OrgUnit": {"Id": 1, "Name": "Logical Programming", "Code": "C003783A_2025"}},
        {"OrgUnit": {"Id": 2, "Name": "Information Security", "Code": "E019400B_2026"}},
    ]
    monkeypatch.setattr(mcp_server, "_call", lambda *args: data)

    result = mcp_server.list_courses(query="logical")

    assert [item["OrgUnit"]["Id"] for item in result] == [1]


def test_mcp_exposes_course_understanding_tools():
    async def scenario():
        async with Client(mcp_server.mcp) as client:
            result = await client.list_tools()
            names = {tool.name for tool in result.tools}
            assert "get_course_overview" in names
            assert "get_course_context" in names
            assert "search_course_content" in names
            assert "read_course_material" in names

    asyncio.run(scenario())
