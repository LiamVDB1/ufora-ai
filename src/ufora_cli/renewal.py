"""Headless token renewal that finishes the SSO chain instead of waiting for it.

Upstream d2l-cli opens ``/d2l/home`` headlessly and waits for the page to issue
a Bearer request. That never happens once Ufora's server-side session has
timed out: the browser is parked on UGent's landing page, then on Microsoft's
account picker, both of which need a click. This module drives those steps
through :mod:`ufora_cli.sso`, captures the token exactly as upstream does, and
reports where the chain stopped when it fails.
"""

from __future__ import annotations

import contextlib
import importlib
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import click

from . import session, sso

HEADLESS_WAIT_SECONDS = 60
POLL_INTERVAL_MS = 500
MAX_STEP_REPEATS = 3
DEBUG_ENV = "UFORA_REFRESH_DEBUG"
DEBUG_DIRNAME = "debug"
HOME_PATH = "/d2l/home"


@dataclass(frozen=True)
class RenewalResult:
    ok: bool
    detail: str
    steps: tuple[str, ...] = ()


@dataclass
class Diagnostics:
    """Trace of the sign-in chain: redacted URLs, titles and screenshots only."""

    directory: Path | None = None
    echo: Callable[[str], None] | None = None
    started: float = field(default_factory=time.monotonic)
    screenshots: int = 0

    @classmethod
    def from_flags(cls, debug: bool, *, root: Path | None = None) -> Diagnostics:
        if not debug and not os.environ.get(DEBUG_ENV):
            return cls()
        base = (root or session.state_dir()) / DEBUG_DIRNAME
        base.mkdir(mode=0o700, parents=True, exist_ok=True)
        base.chmod(0o700)
        directory = base / time.strftime("%Y%m%d-%H%M%S")
        directory.mkdir(mode=0o700, exist_ok=True)
        return cls(directory=directory, echo=lambda line: click.echo(line, err=True))

    @property
    def enabled(self) -> bool:
        return self.directory is not None

    def trace(self, kind: str, message: str) -> None:
        line = f"[{time.monotonic() - self.started:5.1f}s] {kind}: {message}"
        if self.echo:
            self.echo(line)
        if self.directory:
            with contextlib.suppress(OSError):
                fd = os.open(self.directory / "trace.log", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
                with os.fdopen(fd, "a", encoding="utf-8") as handle:
                    handle.write(line + "\n")

    def screenshot(self, page, tag: str) -> None:
        if not self.directory:
            return
        self.screenshots += 1
        target = self.directory / f"{self.screenshots:02d}-{tag}.png"
        with contextlib.suppress(Exception):
            page.screenshot(path=str(target))
            target.chmod(0o600)  # the account picker shows the signed-in address


def _playwright():
    from playwright.sync_api import sync_playwright

    return sync_playwright()


def renew_headless(channel: str = "auto", *, diagnostics: Diagnostics | None = None) -> RenewalResult:
    """Renew the token from the saved sign-in without a visible browser."""
    diag = diagnostics or Diagnostics()
    auth_cmd = importlib.import_module("d2l.commands.auth_cmd")
    config = importlib.import_module("d2l.config")
    lms_host = None
    with contextlib.suppress(Exception):
        lms_host = config.get_lms_host()
    if not lms_host:
        return RenewalResult(False, "no Brightspace host configured (set D2L_HOST or run `ufora setup`)")
    try:
        playwright = _playwright()
    except ImportError:
        return RenewalResult(False, "Playwright is not installed")

    captured: dict[str, object] = {}
    with playwright as p:
        context, launch = auth_cmd._launch_context(p, config.BROWSER_PROFILE, True, channel)
        if context is None:
            return RenewalResult(False, "could not launch a browser: " + "; ".join(str(e).strip() for e in launch))
        diag.trace("launch", str(launch))
        session.set_save_on_close(context, False)
        try:
            context.on("request", _bearer_listener(captured, auth_cmd, diag))
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(f"{lms_host}{HOME_PATH}", wait_until="domcontentloaded")
            result = _drive(context, page, captured, lms_host, auth_cmd, diag)
        finally:
            session.set_save_on_close(context, bool(captured))
            context.close()

    if captured:
        auth_cmd._save_token(captured["token"], captured["claims"], config.TOKEN_FILE, config.TOKEN_DIR)
    return result


def _bearer_listener(captured: dict, auth_cmd, diag: Diagnostics):
    def on_request(request) -> None:
        if captured:
            return
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer eyJ"):
            return
        claims = auth_cmd._parse_token(auth.removeprefix("Bearer "))
        if claims:
            captured.update(token=auth.removeprefix("Bearer "), claims=claims)
            diag.trace("token", f"captured from a request to {sso.redact_url(request.url)}")

    return on_request


def _drive(context, page, captured: dict, lms_host: str, auth_cmd, diag: Diagnostics) -> RenewalResult:
    lms_netloc = urlsplit(lms_host).netloc.lower()
    deadline = time.monotonic() + HEADLESS_WAIT_SECONDS
    steps: list[str] = []
    last_seen = ""
    while not captured and time.monotonic() < deadline:
        page = context.pages[-1] if context.pages else page
        url = page.url  # one snapshot: the page may navigate while we look at it
        where = sso.describe_page(page, url=url)
        if where != last_seen:
            diag.trace("page", where)
            diag.screenshot(page, "page")
            last_seen = where

        if sso.host_of(url) == lms_netloc:
            if _capture_from_lms_page(page, captured, auth_cmd, diag):
                break
        else:
            try:
                step = sso.advance(page)
            except sso.InteractiveSignInRequired as exc:
                diag.trace("stop", str(exc))
                return RenewalResult(False, f"{exc} (at {where})", tuple(steps))
            if step:
                steps.append(step)
                diag.trace("step", step)
                if steps.count(step) > MAX_STEP_REPEATS:
                    return RenewalResult(False, f"kept returning to {where} after: {step}", tuple(steps))
                with contextlib.suppress(Exception):
                    page.wait_for_load_state("domcontentloaded")
        with contextlib.suppress(Exception):
            page.wait_for_timeout(POLL_INTERVAL_MS)

    if captured:
        return RenewalResult(True, "token captured", tuple(steps))
    return RenewalResult(False, f"timed out at {last_seen or 'launch'}", tuple(steps))


def _capture_from_lms_page(page, captured: dict, auth_cmd, diag: Diagnostics) -> bool:
    for source, extract in (
        ("local storage", auth_cmd._extract_token_from_local_storage),
        ("the Brightspace auth endpoint", auth_cmd._request_token_in_page),
    ):
        result = extract(page)
        if result:
            captured.update(token=result[0], claims=result[1])
            diag.trace("token", f"captured from {source}")
            return True
    return False


def wrap_capture_and_save(original):
    """Route upstream's headless captures (e.g. automatic CLI refresh) through the SSO-aware flow."""

    def capture_and_save(headless, channel="auto", quiet=False):
        if not headless:
            return original(headless=headless, channel=channel, quiet=quiet)
        result = renew_headless(channel, diagnostics=Diagnostics.from_flags(False))
        if not quiet:
            click.echo(result.detail if result.ok else failure_message(result), err=not result.ok)
        return result.ok

    return capture_and_save


def failure_message(result: RenewalResult) -> str:
    """Explain a failed renewal without revealing any credential."""
    lines = ["Your Ufora session needs a fresh sign-in. Run: ufora login"]
    lines.append(f"  headless renewal {result.detail}")
    if result.steps:
        lines.append("  steps taken: " + "; ".join(result.steps))
    lines.append("  " + last_renewal_summary())
    return "\n".join(lines)


def last_renewal_summary() -> str:
    auth = importlib.import_module("d2l.auth")
    info: dict = {}
    with contextlib.suppress(Exception):
        info = auth.token_info()
    if info.get("status") not in {"valid", "expired"}:
        return "last successful renewal: never on this machine"
    state = "valid until" if info.get("status") == "valid" else "expired"
    return f"last successful renewal: {info.get('captured_at')} (token {state} {info.get('expires_at')})"
