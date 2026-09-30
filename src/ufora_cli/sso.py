"""Deterministic clicks that finish UGent's Ufora sign-in chain headlessly.

Once Ufora's own session has timed out, ``/d2l/home`` redirects to UGent's
landing page on elosp.ugent.be. Its "Ufora login" link starts SAML through
welkom.ugent.be and Microsoft Entra; with a live Microsoft session the only
page left is the account picker, which shows the signed-in account as a tile.
Neither page is an error, but neither advances without a click, so a purely
passive headless browser sits on the landing page until it times out.

Only unambiguous steps are automated: the single landing-page link, a single
signed-in account tile, and the "Stay signed in?" prompt. A page that asks for
a credential or a choice raises instead, so the caller can fail loudly.
"""

from __future__ import annotations

import contextlib
from urllib.parse import urlsplit

LANDING_HOST = "elosp.ugent.be"
MICROSOFT_HOST = "login.microsoftonline.com"

LANDING_LOGIN_LINK = "a#ugent-login-button:visible"
ACCOUNT_TILE = "div.table[role='button'][data-test-id]:visible"
KMSI_CHECKBOX = "#KmsiCheckboxField"
PRIMARY_BUTTON = "#idSIButton9:visible"
CREDENTIAL_FIELDS = "input[type='password']:visible, input[name='loginfmt']:visible, input[name='otc']:visible"
CLICK_TIMEOUT_MS = 5000


class InteractiveSignInRequired(RuntimeError):
    """The page needs a credential or a choice that must not be automated."""


def redact_url(url: str) -> str:
    """Drop query and fragment: SAML/OAuth parameters carry session state."""
    parts = urlsplit(url)
    if not parts.scheme:
        return url
    return f"{parts.scheme}://{parts.netloc}{parts.path}"


def host_of(url: str) -> str:
    return urlsplit(url).netloc.lower()


def page_host(page) -> str:
    return host_of(page.url)


def describe_page(page, *, url: str | None = None) -> str:
    """Return the page's redacted URL plus its title, never its content."""
    title = ""
    with contextlib.suppress(Exception):
        title = str(page.title()).strip()
    location = redact_url(page.url if url is None else url)
    return f"{location} ({title[:60]!r})" if title else location


def advance(page) -> str | None:
    """Perform at most one deterministic step; describe it, or return None.

    Raises InteractiveSignInRequired when the page cannot be passed without a
    person. A click that fails because the page is already navigating away is
    treated as "nothing done": the caller polls again after the navigation.
    """
    host = page_host(page)
    if host == LANDING_HOST:
        return _advance_landing(page)
    if host == MICROSOFT_HOST:
        return _advance_microsoft(page)
    return None


def _advance_landing(page) -> str | None:
    if _count(page, LANDING_LOGIN_LINK) == 1 and _click(page, LANDING_LOGIN_LINK):
        return "followed the 'Ufora login' link on the UGent landing page"
    return None


def _advance_microsoft(page) -> str | None:
    if _count(page, CREDENTIAL_FIELDS):
        raise InteractiveSignInRequired(
            "Microsoft asks for a credential, so the saved sign-in is no longer valid"
        )
    tiles = _count(page, ACCOUNT_TILE)
    if tiles > 1:
        raise InteractiveSignInRequired(
            f"Microsoft lists {tiles} accounts; choose one during a visible `ufora login`"
        )
    if tiles == 1 and _click(page, ACCOUNT_TILE):
        return "picked the single signed-in Microsoft account"
    if _count(page, KMSI_CHECKBOX) and _count(page, PRIMARY_BUTTON) and _click(page, PRIMARY_BUTTON):
        return "answered 'Stay signed in?' with Yes"
    return None


def _count(page, selector: str) -> int:
    with contextlib.suppress(Exception):
        return int(page.locator(selector).count())
    return 0


def _click(page, selector: str) -> bool:
    with contextlib.suppress(Exception):
        page.locator(selector).first.click(timeout=CLICK_TIMEOUT_MS)
        return True
    return False
