from __future__ import annotations

import pytest
from click.testing import CliRunner

from ufora_cli import cli as cli_module
from ufora_cli import core as core_module
from ufora_cli import course_context, mcp_server


@pytest.fixture(autouse=True)
def _no_saved_sign_in(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep this machine's real ~/.d2l out of login tests; tests opt in explicitly."""
    monkeypatch.setattr(cli_module, "_has_saved_sign_in", lambda: False)


def _fake_login_env(monkeypatch: pytest.MonkeyPatch, *, ssh: bool = False, graphical: bool = True) -> list[list[str]]:
    """Stub everything around `ufora login` and record visible-login invocations."""
    visible: list[list[str]] = []
    monkeypatch.setattr(cli_module, "harden_d2l_state", lambda **kwargs: None)
    monkeypatch.setattr(cli_module, "clear_stale_chromium_locks", lambda profile: False)
    monkeypatch.setattr(cli_module, "is_ssh_session", lambda env=None: ssh)
    monkeypatch.setattr(cli_module, "inherit_graphical_session", lambda env: dict(env))
    monkeypatch.setattr(cli_module, "has_graphical_session", lambda env=None: graphical)
    monkeypatch.setattr(
        cli_module,
        "run_d2l_passthrough",
        lambda args, interactive=False, env=None: visible.append(list(args)) or 0,
    )
    return visible


def _fake_renewal(monkeypatch: pytest.MonkeyPatch, code: int, out: str = "", err: str = "") -> list[list[str]]:
    calls: list[list[str]] = []
    monkeypatch.setattr(cli_module, "_has_saved_sign_in", lambda: True)
    monkeypatch.setattr(
        cli_module,
        "run_d2l_captured",
        lambda args, timeout=0: calls.append(list(args)) or (code, out, err),
    )
    return calls


def test_logout_clears_only_local_auth_state(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(cli_module, "clear_auth_state", lambda: ["token.json", "browser_profile"])

    result = CliRunner().invoke(cli_module.cli, ["logout"])

    assert result.exit_code == 0, result.output
    assert "token.json" in result.output
    assert "browser_profile" in result.output
    assert "does not revoke" in result.output.lower()


def test_mcp_command_forwards_transport(monkeypatch: pytest.MonkeyPatch):
    seen = {}

    def fake_run_server(**kwargs):
        seen.update(kwargs)

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


def test_direct_cli_errors_strip_terminal_control_characters(monkeypatch: pytest.MonkeyPatch):
    from ufora_cli import materials

    monkeypatch.setattr(
        materials,
        "get_course_overview",
        lambda _course: (_ for _ in ()).throw(RuntimeError("Bad\x1b]52;c;clipboard\x07 title")),
    )
    result = CliRunner().invoke(cli_module.cli, ["overview", "TEST"])

    assert result.exit_code != 0
    assert "\x1b" not in result.output
    assert "\x07" not in result.output
    assert "Bad]52;c;clipboard title" in result.output


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
    text = skill.read_text(encoding="utf-8")
    assert "# Ufora AI" in text
    assert "read_course_material" in text


def test_login_fails_closed_without_display(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []
    monkeypatch.setattr(cli_module, "harden_d2l_state", lambda **kwargs: None)
    monkeypatch.setattr(cli_module, "clear_stale_chromium_locks", lambda profile: False)
    monkeypatch.setattr(cli_module, "is_ssh_session", lambda env=None: False)
    monkeypatch.setattr(cli_module, "inherit_graphical_session", lambda env: dict(env))
    monkeypatch.setattr(cli_module, "has_graphical_session", lambda env=None: False)
    monkeypatch.setattr(
        cli_module,
        "run_d2l_passthrough",
        lambda args, interactive=False, env=None: seen.append(list(args)) or 0,
    )

    result = CliRunner().invoke(cli_module.cli, ["login"])

    assert result.exit_code != 0
    assert "No graphical display" in result.output
    assert seen == []


def test_login_ssh_without_display_does_not_open_local_gnome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[list[str]] = []
    monkeypatch.setattr(cli_module, "harden_d2l_state", lambda **kwargs: None)
    monkeypatch.setattr(cli_module, "clear_stale_chromium_locks", lambda profile: False)
    monkeypatch.setattr(cli_module, "has_graphical_session", lambda env=None: False)
    monkeypatch.setattr(cli_module, "is_ssh_session", lambda env=None: True)
    monkeypatch.setattr(
        cli_module,
        "inherit_graphical_session",
        lambda env: {**env, "DISPLAY": ":2"},
    )
    monkeypatch.setattr(
        cli_module,
        "run_d2l_passthrough",
        lambda args, interactive=False, env=None: seen.append(list(args)) or 0,
    )

    result = CliRunner().invoke(cli_module.cli, ["login"])

    assert result.exit_code != 0
    assert "SSH session has no forwarded display" in result.output
    assert seen == []


def test_login_passes_inherited_display_to_browser(monkeypatch: pytest.MonkeyPatch):
    seen: list[tuple[list[str], dict[str, str]]] = []
    monkeypatch.setattr(cli_module, "harden_d2l_state", lambda **kwargs: None)
    monkeypatch.setattr(cli_module, "clear_stale_chromium_locks", lambda profile: False)
    monkeypatch.setattr(cli_module, "is_ssh_session", lambda env=None: False)
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr(
        cli_module,
        "has_graphical_session",
        lambda env=None: core_module.has_graphical_session(env, platform="linux"),
    )
    monkeypatch.setattr(cli_module, "inherit_graphical_session", lambda env: {**env, "DISPLAY": ":2"})
    monkeypatch.setattr(
        cli_module,
        "run_d2l_passthrough",
        lambda args, interactive=False, env=None: seen.append((list(args), dict(env or {}))) or 0,
    )

    result = CliRunner().invoke(cli_module.cli, ["--json", "login", "--channel", "chrome"])

    assert result.exit_code == 0, result.output
    assert seen[0][0] == ["login", "--channel", "chrome"]
    assert seen[0][1]["DISPLAY"] == ":2"


def test_login_on_macos_desktop_opens_browser_without_display(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[list[str]] = []
    monkeypatch.setattr(cli_module, "harden_d2l_state", lambda **kwargs: None)
    monkeypatch.setattr(cli_module, "clear_stale_chromium_locks", lambda profile: False)
    for key in ("DISPLAY", "WAYLAND_DISPLAY", "SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(
        cli_module,
        "has_graphical_session",
        lambda env=None: core_module.has_graphical_session(env, platform="darwin"),
    )
    monkeypatch.setattr(
        cli_module,
        "run_d2l_passthrough",
        lambda args, interactive=False, env=None: seen.append(list(args)) or 0,
    )

    result = CliRunner().invoke(cli_module.cli, ["login"])

    assert result.exit_code == 0, result.output
    assert seen == [["login", "--channel", "auto"]]


def test_refresh_forwards_to_internal_refresh(monkeypatch: pytest.MonkeyPatch):
    seen: list[list[str]] = []
    monkeypatch.setattr(cli_module, "harden_d2l_state", lambda **kwargs: None)
    monkeypatch.setattr(
        cli_module,
        "run_d2l_passthrough",
        lambda args, interactive=False, env=None: seen.append(list(args)) or 0,
    )

    result = CliRunner().invoke(cli_module.cli, ["refresh"])

    assert result.exit_code == 0, result.output
    assert seen == [["refresh"]]


def test_refresh_debug_flag_is_forwarded(monkeypatch: pytest.MonkeyPatch):
    seen: list[list[str]] = []
    monkeypatch.setattr(cli_module, "harden_d2l_state", lambda **kwargs: None)
    monkeypatch.setattr(
        cli_module,
        "run_d2l_passthrough",
        lambda args, interactive=False, env=None: seen.append(list(args)) or 0,
    )

    result = CliRunner().invoke(cli_module.cli, ["refresh", "--debug"])

    assert result.exit_code == 0, result.output
    assert seen == [["refresh", "--debug"]]


def test_session_export_and_import_round_trip(monkeypatch: pytest.MonkeyPatch, tmp_path):
    import json
    import time

    from ufora_cli import session, session_transfer

    monkeypatch.setattr(cli_module, "harden_d2l_state", lambda **kwargs: None)
    laptop, server = tmp_path / "laptop", tmp_path / "server"
    laptop.mkdir()
    exp = int(time.time()) + 3000

    monkeypatch.setattr(session.Path, "home", lambda: laptop)
    session.save_session_cookies([{"name": "ESTSAUTH", "value": "x", "domain": ".login.microsoftonline.com", "path": "/"}])
    session_transfer.token_file().write_text(json.dumps({"token": "eyJ.secret", "exp": exp}))
    bundle_path = tmp_path / "bundle.json"
    result = CliRunner().invoke(cli_module.cli, ["session", "export", str(bundle_path)])
    assert result.exit_code == 0, result.output
    assert "1 sign-in cookies with a token" in result.output
    assert oct(bundle_path.stat().st_mode & 0o777) == "0o600"

    monkeypatch.setattr(session.Path, "home", lambda: server)
    (server / ".d2l").mkdir(parents=True)
    session.save_session_cookies([{"name": "d2lSessionVal", "value": "s", "domain": "ufora.ugent.be", "path": "/"}])
    result = CliRunner().invoke(cli_module.cli, ["session", "import", str(bundle_path)])
    assert result.exit_code == 0, result.output
    assert "Imported 1 sign-in cookies (2 saved)" in result.output
    assert "Token replaced" in result.output
    assert json.loads(session_transfer.token_file().read_text())["exp"] == exp
    assert "secret" not in result.output


def test_session_import_via_stdin_rejects_garbage(monkeypatch: pytest.MonkeyPatch, tmp_path):
    from ufora_cli import session

    monkeypatch.setattr(session.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(cli_module, "harden_d2l_state", lambda **kwargs: None)

    result = CliRunner().invoke(cli_module.cli, ["session", "import", "-"], input='{"hello": 1}')

    assert result.exit_code != 0
    assert "not a Ufora session bundle" in result.output


def test_login_reuses_saved_sign_in_without_a_window(monkeypatch: pytest.MonkeyPatch) -> None:
    visible = _fake_login_env(monkeypatch)
    renewals = _fake_renewal(monkeypatch, 0, out="Ufora token renewed; valid until Fri Oct  2 14:00:00 2026.\n")

    result = CliRunner().invoke(cli_module.cli, ["login"])

    assert result.exit_code == 0, result.output
    assert renewals == [["refresh"]]
    assert visible == []
    assert "valid until" in result.output


def test_login_opens_window_when_saved_sign_in_needs_a_password(monkeypatch: pytest.MonkeyPatch) -> None:
    visible = _fake_login_env(monkeypatch)
    _fake_renewal(
        monkeypatch,
        1,
        err=(
            "Your Ufora session needs a fresh sign-in. Run: ufora login\n"
            "  headless renewal Microsoft asks for a credential (at https://login.microsoftonline.com/x)\n"
        ),
    )

    result = CliRunner().invoke(cli_module.cli, ["login", "--channel", "chrome"])

    assert result.exit_code == 0, result.output
    assert visible == [["login", "--channel", "chrome"]]
    assert "Microsoft asks for a credential" in result.output
    assert "Run: ufora login" not in result.output


def test_login_interactive_skips_saved_sign_in(monkeypatch: pytest.MonkeyPatch) -> None:
    visible = _fake_login_env(monkeypatch)
    renewals = _fake_renewal(monkeypatch, 0)

    result = CliRunner().invoke(cli_module.cli, ["login", "--interactive"])

    assert result.exit_code == 0, result.output
    assert renewals == []
    assert visible == [["login", "--channel", "auto"]]


def test_login_without_saved_sign_in_goes_straight_to_window(monkeypatch: pytest.MonkeyPatch) -> None:
    visible = _fake_login_env(monkeypatch)
    calls: list[list[str]] = []
    monkeypatch.setattr(cli_module, "run_d2l_captured", lambda args, timeout=0: calls.append(list(args)) or (0, "", ""))

    result = CliRunner().invoke(cli_module.cli, ["login"])

    assert result.exit_code == 0, result.output
    assert calls == []
    assert visible == [["login", "--channel", "auto"]]


def test_login_over_ssh_succeeds_from_saved_sign_in(monkeypatch: pytest.MonkeyPatch) -> None:
    visible = _fake_login_env(monkeypatch, ssh=True, graphical=False)
    _fake_renewal(monkeypatch, 0, out="Ufora token renewed.\n")

    result = CliRunner().invoke(cli_module.cli, ["login"])

    assert result.exit_code == 0, result.output
    assert visible == []


def test_login_over_ssh_explains_session_transfer_when_password_needed(monkeypatch: pytest.MonkeyPatch) -> None:
    visible = _fake_login_env(monkeypatch, ssh=True, graphical=False)
    _fake_renewal(monkeypatch, 1, err="  headless renewal timed out at launch\n")

    result = CliRunner().invoke(cli_module.cli, ["login"])

    assert result.exit_code != 0
    assert "ufora session export" in result.output
    assert visible == []


def test_login_rejects_headless_with_interactive(monkeypatch: pytest.MonkeyPatch) -> None:
    visible = _fake_login_env(monkeypatch)

    result = CliRunner().invoke(cli_module.cli, ["login", "--headless", "--interactive"])

    assert result.exit_code != 0
    assert visible == []
