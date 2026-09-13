from __future__ import annotations

from click.testing import CliRunner
import pytest

from ufora_cli import cli as cli_module


def test_mcp_command_forwards_transport(monkeypatch: pytest.MonkeyPatch):
    seen = {}

    def fake_run_server(**kwargs):
        seen.update(kwargs)

    import ufora_cli.mcp_server as mcp_server

    monkeypatch.setattr(mcp_server, "run_server", fake_run_server)
    result = CliRunner().invoke(
        cli_module.cli,
        ["mcp", "--transport", "http", "--host", "127.0.0.1", "--port", "9999", "--path", "/u"],
    )

    assert result.exit_code == 0, result.output
    assert seen == {
        "transport": "http",
        "host": "127.0.0.1",
        "port": 9999,
        "path": "/u",
    }


def test_mcp_command_surfaces_security_refusal(monkeypatch: pytest.MonkeyPatch):
    import ufora_cli.mcp_server as mcp_server

    def fail(**kwargs):
        raise ValueError("loopback only")

    monkeypatch.setattr(mcp_server, "run_server", fail)
    result = CliRunner().invoke(cli_module.cli, ["mcp", "--transport", "http", "--host", "0.0.0.0"])

    assert result.exit_code != 0
    assert "loopback only" in result.output


def test_courses_accepts_search_query_and_includes_historical_matches(monkeypatch: pytest.MonkeyPatch):
    enrollments = [
        {
            "OrgUnit": {
                "Id": 1202761,
                "Name": "C003783A - Logisch programmeren",
                "Code": "C003783A_2025",
            },
            "Access": {"IsActive": True},
        },
        {
            "OrgUnit": {
                "Id": 1395038,
                "Name": "E017950A - Secure Software and Systems",
                "Code": "E017950A_2026",
            },
            "Access": {"IsActive": True},
        },
    ]
    monkeypatch.setattr(cli_module, "run_d2l_json", lambda args: enrollments)

    result = CliRunner().invoke(cli_module.cli, ["courses", "Logisch"])

    assert result.exit_code == 0, result.output
    assert "Logisch programmeren" in result.output
    assert "Secure Software" not in result.output


def test_courses_search_surfaces_backend_failure_without_traceback(monkeypatch: pytest.MonkeyPatch):
    def fail(_args):
        raise RuntimeError("Your Ufora session needs a fresh sign-in. Run: ufora login")

    monkeypatch.setattr(cli_module, "run_d2l_json", fail)
    result = CliRunner().invoke(cli_module.cli, ["courses", "Logisch"])

    assert result.exit_code != 0
    assert "Error: Your Ufora session needs a fresh sign-in. Run: ufora login" in result.output
    assert "Traceback" not in result.output


def test_courses_search_json_is_machine_readable(monkeypatch: pytest.MonkeyPatch):
    enrollments = [
        {
            "OrgUnit": {"Id": 1, "Name": "Logical Programming", "Code": "TEST_2025"},
            "Access": {"IsActive": True},
        }
    ]
    monkeypatch.setattr(cli_module, "run_d2l_json", lambda args: enrollments)

    result = CliRunner().invoke(cli_module.cli, ["--json", "courses", "logical"])

    assert result.exit_code == 0, result.output
    assert '"Name": "Logical Programming"' in result.output


def test_news_without_course_uses_real_course_announcement_aggregator(monkeypatch: pytest.MonkeyPatch):
    import ufora_cli.course_context as course_context

    seen = {}

    def fake_get_announcements(course=None, *, since=None):
        seen.update({"course": course, "since": since})
        return [
            {
                "Course": {"name": "Logical Programming", "code": "TEST_2026"},
                "Title": "Project update",
                "StartDate": "2026-09-13T10:00:00.000Z",
                "Body": {"Text": "Read the updated project brief."},
            }
        ]

    monkeypatch.setattr(course_context, "get_announcements", fake_get_announcements)
    result = CliRunner().invoke(cli_module.cli, ["news", "--since", "2026-09-01"])

    assert result.exit_code == 0, result.output
    assert seen == {"course": None, "since": "2026-09-01"}
    assert "Logical Programming" in result.output
    assert "Project update" in result.output
    assert "Read the updated project brief." in result.output


def test_skill_install_writes_bundled_skill(tmp_path):
    destination = tmp_path / "skills" / "ufora"
    result = CliRunner().invoke(
        cli_module.cli,
        ["skill", "install", "--destination", str(destination)],
    )

    assert result.exit_code == 0, result.output
    skill = destination / "SKILL.md"
    assert skill.exists()
    text = skill.read_text()
    assert "# Ufora AI" in text
    assert "read_course_material" in text
