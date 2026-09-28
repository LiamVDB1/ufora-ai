from __future__ import annotations

import os
import subprocess
from types import SimpleNamespace

import pytest

from ufora_cli import core
from ufora_cli.core import UpstreamCommandError, _translate_upstream_text


def test_upstream_command_names_do_not_leak_to_users():
    text = (
        "Your D2L session needs a fresh sign-in. Run: d2l login. "
        "Then run d2l courses. Run 'd2l assignments COURSE' to inspect work."
    )
    translated = _translate_upstream_text(text)

    assert "d2l login" not in translated
    assert "d2l courses" not in translated
    assert "d2l assignments" not in translated
    assert "ufora login" in translated
    assert "ufora courses" in translated
    assert "ufora assignments COURSE" in translated
    assert "Ufora session" in translated
    assert "D2L" not in translated


def test_expired_auth_status_is_user_facing_session_language():
    translated = _translate_upstream_text("[*] D2L token expired — refreshing sign-in in the background...")

    assert translated == "[*] Ufora session expired — trying the saved sign-in in the background..."


def test_ufora_env_forces_ugent_host_and_drops_ambient_token():
    env = core.ufora_env(
        {
            "D2L_HOST": "https://example.invalid",
            "D2L_TOKEN": "ambient-token-that-must-not-be-inherited",
            "KEEP": "yes",
        }
    )

    assert env["D2L_HOST"] == core.UFORA_HOST
    assert "D2L_TOKEN" not in env
    assert env["KEEP"] == "yes"


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits are not authoritative on Windows")
def test_harden_d2l_state_applies_private_posix_modes(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setattr(core.Path, "home", lambda: tmp_path)
    state_dir = tmp_path / ".d2l"
    state_dir.mkdir(mode=0o755)
    token_file = state_dir / "token.json"
    token_file.write_text("{}", encoding="utf-8")
    token_file.chmod(0o644)

    core.harden_d2l_state()

    assert state_dir.stat().st_mode & 0o777 == 0o700
    assert token_file.stat().st_mode & 0o777 == 0o600


def test_clear_auth_state_removes_cached_token_and_browser_profile(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    monkeypatch.setattr(core.Path, "home", lambda: tmp_path)
    state_dir = tmp_path / ".d2l"
    browser_profile = state_dir / "browser_profile"
    browser_profile.mkdir(parents=True)
    (browser_profile / "Cookies").write_text("session", encoding="utf-8")
    (state_dir / "token.json").write_text('{"token":"secret"}', encoding="utf-8")

    (state_dir / "session.json").write_text('{"cookies":[]}', encoding="utf-8")

    removed = core.clear_auth_state()

    assert removed == ["token.json", "session.json", "browser_profile"]
    assert not (state_dir / "session.json").exists()
    assert not (state_dir / "token.json").exists()
    assert not browser_profile.exists()
    assert state_dir.exists()


def test_clear_auth_state_unlinks_browser_profile_symlink_without_following_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    monkeypatch.setattr(core.Path, "home", lambda: tmp_path)
    state_dir = tmp_path / ".d2l"
    state_dir.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = outside / "keep"
    marker.write_text("safe", encoding="utf-8")
    (state_dir / "browser_profile").symlink_to(outside, target_is_directory=True)

    core.clear_auth_state()

    assert marker.read_text(encoding="utf-8") == "safe"
    assert not (state_dir / "browser_profile").exists()


def test_run_json_decodes_payload_and_uses_no_shell(monkeypatch: pytest.MonkeyPatch):
    seen = {}

    def fake_run(command, **kwargs):
        seen.update({"command": command, **kwargs})
        return SimpleNamespace(
            returncode=0,
            stdout='{"ok": true, "title": "safe\\u001b]52;c;clipboard\\u0007"}\n',
            stderr="",
        )

    monkeypatch.setattr(core.subprocess, "run", fake_run)

    result = core.run_d2l_json(["courses", "name; echo not-a-shell"], timeout=7)
    assert result == {"ok": True, "title": "safe]52;c;clipboard"}
    assert seen["command"][-2:] == ["courses", "name; echo not-a-shell"]
    assert seen["timeout"] == 7
    assert "shell" not in seen
    assert seen["env"]["D2L_HOST"] == core.UFORA_HOST


def test_run_json_surfaces_translated_upstream_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        core.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=2,
            stdout="",
            stderr="Your D2L session expired. Run: d2l login",
        ),
    )

    with pytest.raises(UpstreamCommandError) as exc_info:
        core.run_d2l_json(["courses"])

    assert exc_info.value.returncode == 2
    assert "Ufora session" in str(exc_info.value)
    assert "ufora login" in str(exc_info.value)
    assert "d2l" not in str(exc_info.value).lower()


def test_run_json_times_out_cleanly(monkeypatch: pytest.MonkeyPatch):
    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd=["ufora"], timeout=3)

    monkeypatch.setattr(core.subprocess, "run", timeout)

    with pytest.raises(UpstreamCommandError, match="timed out after 3 seconds"):
        core.run_d2l_json(["courses"], timeout=3)


def test_run_json_rejects_non_json_and_accepts_empty(monkeypatch: pytest.MonkeyPatch):
    responses = iter(
        [
            SimpleNamespace(returncode=0, stdout="not-json", stderr=""),
            SimpleNamespace(returncode=0, stdout="", stderr=""),
        ]
    )
    monkeypatch.setattr(core.subprocess, "run", lambda *_args, **_kwargs: next(responses))

    with pytest.raises(UpstreamCommandError, match="non-JSON output"):
        core.run_d2l_json(["courses"])
    assert core.run_d2l_json(["courses"]) is None


def test_passthrough_translates_child_output(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    monkeypatch.setattr(
        core.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout="Run d2l courses\x1b]52;c;clipboard\x07\n",
            stderr="D2L token expired\x1b[31m\n",
        ),
    )

    assert core.run_d2l_passthrough(["doctor"]) == 0
    captured = capsys.readouterr()
    assert "ufora courses" in captured.out
    assert "Ufora token expired" in captured.err
    assert "\x1b" not in captured.out + captured.err
    assert "\x07" not in captured.out + captured.err


def test_is_ssh_session_reads_ssh_env() -> None:
    assert core.is_ssh_session({"SSH_CONNECTION": "1.2.3.4 1 5.6.7.8 22"}) is True
    assert core.is_ssh_session({"HOME": "/home/liam"}) is False


def test_inherit_graphical_session_keeps_existing_display() -> None:
    env = core.inherit_graphical_session(
        {"HOME": "/home/liam", "DISPLAY": ":1"},
        discovered={"DISPLAY": ":2", "WAYLAND_DISPLAY": "wayland-0"},
    )

    assert env["DISPLAY"] == ":1"
    assert "WAYLAND_DISPLAY" not in env


def test_inherit_graphical_session_copies_discovered_display() -> None:
    env = core.inherit_graphical_session(
        {"HOME": "/home/liam"},
        discovered={
            "DISPLAY": ":2",
            "WAYLAND_DISPLAY": "wayland-0",
            "XAUTHORITY": "/run/user/1000/.mutter-Xwaylandauth.abc",
        },
    )

    assert env["DISPLAY"] == ":2"
    assert env["WAYLAND_DISPLAY"] == "wayland-0"
    assert env["XAUTHORITY"].endswith(".abc")


def test_clear_stale_chromium_locks_removes_dead_pid_lock(tmp_path) -> None:
    profile = tmp_path / "browser_profile"
    profile.mkdir()
    (profile / "SingletonLock").symlink_to("macserver-99999999")
    (profile / "SingletonCookie").symlink_to("stale")

    assert core.clear_stale_chromium_locks(profile) is True
    assert not (profile / "SingletonLock").exists()
    assert not (profile / "SingletonCookie").exists()


def test_clear_stale_chromium_locks_keeps_live_pid_lock(tmp_path) -> None:
    profile = tmp_path / "browser_profile"
    profile.mkdir()
    live_pid = os.getpid()
    (profile / "SingletonLock").symlink_to(f"macserver-{live_pid}")

    assert core.clear_stale_chromium_locks(profile) is False
    assert (profile / "SingletonLock").is_symlink()
