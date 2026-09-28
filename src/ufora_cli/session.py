"""Keep the Ufora sign-in alive across headless browser launches.

Brightspace API tokens live about an hour. Upstream d2l-cli renews them by
reopening the saved browser profile headlessly, but Chromium discards session
cookies whenever a browser closes. Ufora's own session and the UGent/Microsoft
SSO sessions behind it are exactly such cookies, so every silent renewal used
to start signed out and fail. This module saves those cookies when a login or
refresh browser closes and restores them on the next launch.
"""

from __future__ import annotations

import contextlib
import json
import os
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .core import D2L_STATE_DIRNAME, clear_stale_chromium_locks

SESSION_FILENAME = "session.json"
LOCK_FILENAME = "browser.lock"
# Only the hosts in Ufora's sign-in chain: ufora/elosp/welkom.ugent.be and Microsoft Entra.
SESSION_COOKIE_DOMAINS = ("ugent.be", "microsoftonline.com")
# Never hand out a token that expires this soon; force a fresh one instead.
MIN_TOKEN_LIFETIME_SECONDS = 10 * 60
LOCK_TIMEOUT_SECONDS = 120


def state_dir() -> Path:
    return Path.home() / D2L_STATE_DIRNAME


def session_file() -> Path:
    return state_dir() / SESSION_FILENAME


def is_session_cookie_domain(domain: str) -> bool:
    host = domain.lstrip(".").lower()
    return any(host == allowed or host.endswith(f".{allowed}") for allowed in SESSION_COOKIE_DOMAINS)


def save_session_cookies(cookies: list[dict[str, Any]]) -> int:
    """Persist sign-in cookies privately (0600), replacing the previous set."""
    kept = [cookie for cookie in cookies if is_session_cookie_domain(str(cookie.get("domain", "")))]
    target = session_file()
    target.parent.mkdir(mode=0o700, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    with contextlib.suppress(FileNotFoundError):
        temporary.unlink()
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump({"saved_at": int(time.time()), "cookies": kept}, handle)
    os.replace(temporary, target)
    return len(kept)


def load_session_cookies(*, now: float | None = None) -> list[dict[str, Any]]:
    """Return saved sign-in cookies that have not expired; tolerate a missing/corrupt file."""
    try:
        data = json.loads(session_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    cookies = data.get("cookies") if isinstance(data, dict) else None
    if not isinstance(cookies, list):
        return []
    current = time.time() if now is None else now
    return [
        cookie
        for cookie in cookies
        if isinstance(cookie, dict)
        and is_session_cookie_domain(str(cookie.get("domain", "")))
        and not (0 < float(cookie.get("expires", -1)) <= current)
    ]


@contextlib.contextmanager
def browser_profile_lock(timeout: float = LOCK_TIMEOUT_SECONDS) -> Iterator[None]:
    """Serialize browser launches so a timer refresh and a CLI refresh never collide."""
    try:
        import fcntl
    except ImportError:  # Windows: Chromium's own profile lock is the only guard.
        yield
        return

    path = state_dir() / LOCK_FILENAME
    path.parent.mkdir(mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Another Ufora sign-in browser is still running.") from None
                time.sleep(0.5)
        yield
    finally:
        os.close(fd)


def wrap_launch_context(original):
    """Wrap upstream ``_launch_context`` with locking, cookie restore and cookie save."""

    def launch_context(p, browser_profile, headless, channel):
        lock = browser_profile_lock()
        lock.__enter__()
        try:
            clear_stale_chromium_locks(Path(browser_profile))
            context, detail = original(p, browser_profile, headless, channel)
        except BaseException:
            lock.__exit__(None, None, None)
            raise
        if context is None:
            lock.__exit__(None, None, None)
            return context, detail

        for saved in load_session_cookies():
            # One cookie Playwright rejects must not cost the rest of the session.
            with contextlib.suppress(Exception):
                context.add_cookies([saved])

        close = context.close

        def close_and_save(*args, **kwargs):
            try:
                with contextlib.suppress(Exception):
                    save_session_cookies(context.cookies())
                return close(*args, **kwargs)
            finally:
                lock.__exit__(None, None, None)

        context.close = close_and_save
        return context, detail

    return launch_context


def require_min_lifetime(parse_token):
    """Wrap upstream ``_parse_token`` so nearly expired tokens are never captured."""

    def parse(token):
        claims = parse_token(token)
        if not claims or claims.get("exp", 0) <= time.time() + MIN_TOKEN_LIFETIME_SECONDS:
            return None
        return claims

    return parse
