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
    return {"name": name, "value": "v", "domain": domain, "path": "/", "expires": expires}


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
    assert [c["name"] for c in json.loads(path.read_text())["cookies"]] == ["d2lSessionVal"]


def test_load_drops_expired_but_keeps_session_cookies(home):
    now = time.time()
    session.save_session_cookies(
        [
            cookie("session", "ufora.ugent.be"),
            cookie("fresh", ".ugent.be", now + 3600),
            cookie("stale", ".ugent.be", now - 1),
        ]
    )

    assert [c["name"] for c in session.load_session_cookies(now=now)] == ["session", "fresh"]


def test_load_tolerates_missing_or_corrupt_file(home):
    assert session.load_session_cookies() == []
    (home / ".d2l").mkdir()
    (home / ".d2l" / "session.json").write_text("{not json", encoding="utf-8")
    assert session.load_session_cookies() == []


def test_launch_restores_cookies_and_saves_them_on_close(home, monkeypatch):
    monkeypatch.setattr(session, "clear_stale_chromium_locks", lambda profile: False)
    session.save_session_cookies([cookie("rejected", "ugent.be"), cookie("old", "ufora.ugent.be")])
    context = FakeContext([cookie("renewed", "welkom.ugent.be")])
    launch = session.wrap_launch_context(lambda p, profile, headless, channel: (context, "Chromium"))

    returned, label = launch(None, home / ".d2l" / "browser_profile", True, "auto")
    returned.close()

    assert label == "Chromium"
    assert [c["name"] for c in context.added] == ["old"]
    assert context.closed
    # Closing merges: the renewed cookie joins the saved ones instead of replacing them.
    assert sorted(c["name"] for c in session.load_session_cookies()) == ["old", "rejected", "renewed"]


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
    from click.testing import CliRunner

    from ufora_cli import renewal

    failed = renewal.RenewalResult(False, "timed out at https://elosp.ugent.be/welcome", ("clicked",))
    monkeypatch.setattr(renewal, "renew_headless", lambda channel="auto", *, diagnostics=None: failed)
    monkeypatch.setattr(renewal, "last_renewal_summary", lambda: "last successful renewal: never on this machine")

    result = CliRunner().invoke(d2l_entry.refresh)

    assert result.exit_code == 1
    assert "ufora login" in result.output
    assert "elosp.ugent.be" in result.output
    assert "last successful renewal" in result.output


def test_merge_keeps_unexpired_existing_and_prefers_fresh():
    now = 1_000_000
    existing = [
        cookie("keep", ".ugent.be", expires=now + 100),
        cookie("stale", ".ugent.be", expires=now - 1),
        {**cookie("shared", "ufora.ugent.be"), "value": "old"},
    ]
    fresh = [{**cookie("shared", "ufora.ugent.be"), "value": "new"}, cookie("foreign", "example.com")]

    merged = {c["name"]: c for c in session.merge_session_cookies(existing, fresh, now=now)}

    assert set(merged) == {"keep", "shared"}
    assert merged["shared"]["value"] == "new"


def test_failed_launch_does_not_degrade_saved_session(home):
    session.save_session_cookies([cookie("ESTSAUTH", ".login.microsoftonline.com"), cookie("d2lSessionVal", "ufora.ugent.be")])
    context = FakeContext(cookies=[cookie("d2lSessionVal", "ufora.ugent.be")])
    wrapped = session.wrap_launch_context(lambda p, profile, headless, channel: (context, ["launched"]))

    ctx, _ = wrapped(None, str(home / ".d2l" / "browser_profile"), True, "auto")
    session.set_save_on_close(ctx, False)
    ctx.close()

    assert context.closed
    assert {c["name"] for c in session.load_session_cookies()} == {"ESTSAUTH", "d2lSessionVal"}


def test_close_merges_instead_of_replacing(home):
    session.save_session_cookies([cookie("ESTSAUTH", ".login.microsoftonline.com")])
    context = FakeContext(cookies=[cookie("d2lSessionVal", "ufora.ugent.be")])
    wrapped = session.wrap_launch_context(lambda p, profile, headless, channel: (context, ["launched"]))

    ctx, _ = wrapped(None, str(home / ".d2l" / "browser_profile"), True, "auto")
    ctx.close()

    assert {c["name"] for c in session.load_session_cookies()} == {"ESTSAUTH", "d2lSessionVal"}
    assert session.session_saved_at() > 0
