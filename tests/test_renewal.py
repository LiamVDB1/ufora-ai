from __future__ import annotations

import importlib
import time

import pytest

from ufora_cli import renewal, session, sso

LMS = "https://ufora.ugent.be"


class FakePage:
    """A page whose URL and elements advance when a known selector is clicked."""

    def __init__(self, url: str, elements: dict[str, int] | None = None, flow: dict | None = None):
        self.url = url
        self.elements = dict(elements or {})
        self.flow = dict(flow or {})
        self.clicked: list[str] = []
        self.screenshots: list[str] = []

    def title(self):
        return "Fake"

    def locator(self, selector):
        page = self

        class Locator:
            @property
            def first(self):
                return self

            def count(self):
                return page.elements.get(selector, 0)

            def click(self, timeout=None):
                page.clicked.append(selector)
                target = page.flow[selector]
                page.url, page.elements = target if isinstance(target, tuple) else (target, {})

        return Locator()

    def goto(self, url, wait_until=None):
        self.url = url
        if "goto" in self.flow:
            self.url, self.elements = self.flow["goto"]

    def wait_for_load_state(self, state=None):
        pass

    def wait_for_timeout(self, ms):
        pass

    def screenshot(self, path):
        self.screenshots.append(path)


class FakeContext:
    def __init__(self, page):
        self.pages = [page]
        self.closed = False
        self.listeners = []

    def on(self, event, handler):
        self.listeners.append(handler)

    def close(self):
        self.closed = True


class FakePlaywright:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def upstream(monkeypatch, tmp_path):
    auth_cmd = importlib.import_module("d2l.commands.auth_cmd")
    config = importlib.import_module("d2l.config")
    saved = {}
    monkeypatch.setattr(config, "get_lms_host", lambda: LMS)
    monkeypatch.setattr(config, "BROWSER_PROFILE", str(tmp_path / "profile"))
    monkeypatch.setattr(config, "TOKEN_FILE", str(tmp_path / "token.json"))
    monkeypatch.setattr(config, "TOKEN_DIR", str(tmp_path))
    monkeypatch.setattr(auth_cmd, "_save_token", lambda token, claims, f, d: saved.update(token=token, claims=claims))
    monkeypatch.setattr(auth_cmd, "_extract_token_from_local_storage", lambda page: None)
    monkeypatch.setattr(auth_cmd, "_request_token_in_page", lambda page: None)
    monkeypatch.setattr(renewal, "_playwright", lambda: FakePlaywright())
    monkeypatch.setattr(renewal, "HEADLESS_WAIT_SECONDS", 2)
    return auth_cmd, saved


def install_context(monkeypatch, page):
    auth_cmd = importlib.import_module("d2l.commands.auth_cmd")
    context = FakeContext(page)
    monkeypatch.setattr(auth_cmd, "_launch_context", lambda p, profile, headless, channel: (context, ["fake"]))
    return context


def test_sso_advance_clicks_only_deterministic_steps():
    landing = FakePage(
        "https://elosp.ugent.be/welcome?sessionExpired=1",
        {sso.LANDING_LOGIN_LINK: 1},
        {sso.LANDING_LOGIN_LINK: "https://login.microsoftonline.com/x/oauth2/v2.0/authorize?client_id=1"},
    )
    assert "Ufora login" in sso.advance(landing)
    assert sso.page_host(landing) == sso.MICROSOFT_HOST

    picker = FakePage(landing.url, {sso.ACCOUNT_TILE: 1}, {sso.ACCOUNT_TILE: f"{LMS}/d2l/home"})
    assert "single signed-in" in sso.advance(picker)
    assert picker.url == f"{LMS}/d2l/home"
    assert sso.advance(picker) is None  # LMS host: nothing to click

    with pytest.raises(sso.InteractiveSignInRequired, match="2 accounts"):
        sso.advance(FakePage(landing.url, {sso.ACCOUNT_TILE: 2}))
    with pytest.raises(sso.InteractiveSignInRequired, match="credential"):
        sso.advance(FakePage(landing.url, {sso.CREDENTIAL_FIELDS: 1, sso.ACCOUNT_TILE: 1}))

    kmsi = FakePage(landing.url, {sso.KMSI_CHECKBOX: 1, sso.PRIMARY_BUTTON: 1}, {sso.PRIMARY_BUTTON: f"{LMS}/d2l/home"})
    assert "Stay signed in" in sso.advance(kmsi)


def test_redact_url_strips_saml_parameters():
    assert sso.redact_url("https://a.b/c?SAMLRequest=secret#frag") == "https://a.b/c"
    assert sso.describe_page(FakePage("https://a.b/c?x=1")) == "https://a.b/c ('Fake')"


def test_renew_headless_walks_chain_and_saves_token(monkeypatch, upstream, tmp_path):
    auth_cmd, saved = upstream
    landing = "https://elosp.ugent.be/welcome?sessionExpired=1&target=/d2l/home"
    picker = "https://login.microsoftonline.com/t/oauth2/v2.0/authorize?state=s"
    page = FakePage(
        "about:blank",
        flow={
            "goto": (landing, {sso.LANDING_LOGIN_LINK: 1}),
            sso.LANDING_LOGIN_LINK: (picker, {sso.ACCOUNT_TILE: 1}),
            sso.ACCOUNT_TILE: (LMS + "/d2l/home", {}),
        },
    )
    context = install_context(monkeypatch, page)
    claims = {"exp": int(time.time()) + 3600}
    monkeypatch.setattr(
        auth_cmd,
        "_request_token_in_page",
        lambda p: ("eyJ.token", claims) if p.url.endswith("/d2l/home") else None,
    )
    diagnostics = renewal.Diagnostics.from_flags(True, root=tmp_path)
    monkeypatch.setattr(session, "set_save_on_close", lambda ctx, enabled: setattr(ctx, "save", enabled))

    result = renewal.renew_headless(diagnostics=diagnostics)

    assert result.ok, result
    assert [s.split(" ")[0] for s in result.steps] == ["followed", "picked"]
    assert saved["token"] == "eyJ.token"
    assert context.closed and context.save is True
    trace = (diagnostics.directory / "trace.log").read_text()
    assert "elosp.ugent.be/welcome" in trace and "SAMLRequest" not in trace and "state=s" not in trace
    assert "eyJ" not in trace and page.screenshots


def test_renew_headless_fails_loudly_without_saving(monkeypatch, upstream):
    _, saved = upstream
    page = FakePage("about:blank", flow={"goto": ("https://login.microsoftonline.com/t/login", {sso.CREDENTIAL_FIELDS: 1})})
    context = install_context(monkeypatch, page)
    flags = {}
    monkeypatch.setattr(session, "set_save_on_close", lambda ctx, enabled: flags.update(save=enabled))

    result = renewal.renew_headless()

    assert not result.ok and "credential" in result.detail
    assert saved == {} and context.closed and flags["save"] is False
    assert "ufora login" in renewal.failure_message(result)


def test_renew_headless_times_out_on_landing_page(monkeypatch, upstream):
    page = FakePage("about:blank", flow={"goto": ("https://elosp.ugent.be/welcome", {})})
    install_context(monkeypatch, page)

    result = renewal.renew_headless()

    assert not result.ok and result.detail.startswith("timed out at https://elosp.ugent.be/welcome")


def test_wrap_capture_and_save_only_replaces_headless(monkeypatch):
    calls = []
    wrapped = renewal.wrap_capture_and_save(lambda headless, channel, quiet: calls.append("headed") or True)
    monkeypatch.setattr(renewal, "renew_headless", lambda channel, diagnostics=None: renewal.RenewalResult(True, "ok"))

    assert wrapped(False, "auto", True) and calls == ["headed"]
    assert wrapped(True, "auto", True) and calls == ["headed"]
