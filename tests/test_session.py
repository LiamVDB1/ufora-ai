from __future__ import annotations

import json
import time

import pytest

from ufora_cli import d2l_entry, session


@pytest.fixture
def home(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setattr(session.Path, "home", lambda: tmp_path)
    return tmp_path


def cookie(name: str, domain: str, expires: float = -1) -> dict:
    return {
        "name": name,
        "value": "v",
        "domain": domain,
        "path": "/",
        "expires": expires,
    }


class FakeContext:
    def __init__(self, cookies=None):
        self.added: list[dict] = []
        self.jar = list(cookies or [])
        self.closed = False

    def add_cookies(self, cookies):
        if any(c["name"] == "rejected" for c in cookies):
            raise ValueError("invalid cookie")
        self.added.extend(cookies)

    def cookies(self):
        return self.jar

    def close(self):
        self.closed = True


@pytest.mark.parametrize(
    ("domain", "allowed"),
    [
        ("ufora.ugent.be", True),
        (".ugent.be", True),
        ("welkom.ugent.be", True),
        ("login.microsoftonline.com", True),
        ("evilugent.be", False),
        ("ugent.be.attacker.com", False),
        ("example.com", False),
    ],
)
def test_only_sign_in_chain_domains_are_kept(domain, allowed):
    assert session.is_session_cookie_domain(domain) is allowed


def test_save_is_private_and_filters_foreign_cookies(home):
    saved = session.save_session_cookies(
        [cookie("d2lSessionVal", "ufora.ugent.be"), cookie("tracker", "example.com")]
    )

    path = home / ".d2l" / "session.json"
    assert saved == 1
    assert path.stat().st_mode & 0o777 == 0o600
    assert [c["name"] for c in json.loads(path.read_text())["cookies"]] == [
        "d2lSessionVal"
    ]


def test_load_drops_expired_but_keeps_session_cookies(home):
    now = time.time()
    session.save_session_cookies(
        [
            cookie("session", "ufora.ugent.be"),
            cookie("fresh", ".ugent.be", now + 3600),
            cookie("stale", ".ugent.be", now - 1),
        ]
    )

    assert [c["name"] for c in session.load_session_cookies(now=now)] == [
        "session",
        "fresh",
    ]


def test_load_tolerates_missing_or_corrupt_file(home):
    assert session.load_session_cookies() == []
    (home / ".d2l").mkdir()
    (home / ".d2l" / "session.json").write_text("{not json", encoding="utf-8")
    assert session.load_session_cookies() == []


def test_launch_restores_cookies_and_saves_them_on_close(home, monkeypatch):
    monkeypatch.setattr(session, "clear_stale_chromium_locks", lambda profile: False)
    session.save_session_cookies(
        [cookie("rejected", "ugent.be"), cookie("old", "ufora.ugent.be")]
    )
    context = FakeContext([cookie("renewed", "welkom.ugent.be")])
    launch = session.wrap_launch_context(
        lambda p, profile, headless, channel: (context, "Chromium")
    )

    returned, label = launch(None, home / ".d2l" / "browser_profile", True, "auto")
    returned.close()

    assert label == "Chromium"
    assert [c["name"] for c in context.added] == ["old"]
    assert context.closed
    assert [c["name"] for c in session.load_session_cookies()] == ["renewed"]


def test_launch_lock_is_released_after_close_and_failed_launch(home, monkeypatch):
    monkeypatch.setattr(session, "clear_stale_chromium_locks", lambda profile: False)
    ok = session.wrap_launch_context(lambda *args: (FakeContext(), "Chromium"))
    failed = session.wrap_launch_context(lambda *args: (None, ["no browser"]))

    ok(None, home, True, "auto")[0].close()
    assert failed(None, home, True, "auto") == (None, ["no browser"])
    with session.browser_profile_lock(timeout=1):
        pass


def test_second_browser_waits_for_the_profile_lock(home):
    with (
        session.browser_profile_lock(timeout=1),
        pytest.raises(TimeoutError),
        session.browser_profile_lock(timeout=0.2),
    ):
        pass


def test_nearly_expired_tokens_are_not_captured():
    soon = {"exp": int(time.time()) + 60}
    later = {"exp": int(time.time()) + 3600}

    assert session.require_min_lifetime(lambda token: soon)("t") is None
    assert session.require_min_lifetime(lambda token: later)("t") == later
    assert session.require_min_lifetime(lambda token: None)("t") is None


def test_internal_cli_patches_upstream_login_and_exposes_refresh(monkeypatch):
    import importlib

    auth_cmd = importlib.import_module("d2l.commands.auth_cmd")
    monkeypatch.setattr(auth_cmd, "_launch_context", auth_cmd._launch_context)
    monkeypatch.setattr(auth_cmd, "_parse_token", auth_cmd._parse_token)
    original = auth_cmd._launch_context

    d2l_entry._patch_session()

    assert auth_cmd._launch_context is not original
    assert d2l_entry.refresh.name == "refresh"


def test_refresh_failure_asks_for_login(monkeypatch):
    import importlib

    from click.testing import CliRunner

    auth_cmd = importlib.import_module("d2l.commands.auth_cmd")
    monkeypatch.setattr(auth_cmd, "_capture_and_save", lambda **kwargs: False)

    result = CliRunner().invoke(d2l_entry.refresh)

    assert result.exit_code == 1
    assert "ufora login" in result.output


def test_load_saved_token_auto_renews_expired_token(home, monkeypatch):
    import importlib

    state = home / ".d2l"
    state.mkdir(parents=True, exist_ok=True)
    token_file = state / "token.json"

    # Write expired token
    now = time.time()
    token_file.write_text(
        json.dumps(
            {
                "token": "expired.jwt.token",
                "exp": now - 100,
                "sub": "123",
                "tenant": "ugent",
                "captured_at": now - 3600,
            }
        )
    )

    auth_cmd = importlib.import_module("d2l.commands.auth_cmd")
    monkeypatch.setattr(d2l_entry.d2l_auth, "TOKEN_FILE", token_file)

    def fake_attempt_auto_login():
        token_file.write_text(
            json.dumps(
                {
                    "token": "fresh.jwt.token",
                    "exp": now + 3600,
                    "sub": "123",
                    "tenant": "ugent",
                    "captured_at": now,
                }
            )
        )
        return True

    monkeypatch.setattr(auth_cmd, "attempt_auto_login", fake_attempt_auto_login)
    monkeypatch.setattr(
        d2l_entry.d2l_auth,
        "_parse_bearer_claims",
        lambda t: (
            {
                "exp": now - 100,
                "iss": "https://api.brightspace.com/auth",
                "aud": "https://api.brightspace.com/auth/token",
            }
            if "expired" in t
            else {
                "exp": now + 3600,
                "iss": "https://api.brightspace.com/auth",
                "aud": "https://api.brightspace.com/auth/token",
            }
        ),
    )

    token = d2l_entry._load_saved_token_only()
    assert token == "fresh.jwt.token"


def test_load_saved_token_raises_when_auto_renew_fails(home, monkeypatch):
    import importlib

    from d2l.errors import TokenExpiredError

    state = home / ".d2l"
    state.mkdir(parents=True, exist_ok=True)
    token_file = state / "token.json"

    now = time.time()
    token_file.write_text(
        json.dumps(
            {
                "token": "expired.jwt.token",
                "exp": now - 100,
                "sub": "123",
                "tenant": "ugent",
                "captured_at": now - 3600,
            }
        )
    )

    auth_cmd = importlib.import_module("d2l.commands.auth_cmd")
    monkeypatch.setattr(d2l_entry.d2l_auth, "TOKEN_FILE", token_file)
    monkeypatch.setattr(auth_cmd, "attempt_auto_login", lambda: False)
    monkeypatch.setattr(
        d2l_entry.d2l_auth,
        "_parse_bearer_claims",
        lambda t: {
            "exp": now - 100,
            "iss": "https://api.brightspace.com/auth",
            "aud": "https://api.brightspace.com/auth/token",
        },
    )

    with pytest.raises(TokenExpiredError, match="Saved Ufora token is expired"):
        d2l_entry._load_saved_token_only()
