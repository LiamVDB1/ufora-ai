"""Move a sign-in between machines: ``ufora session export`` / ``import``.

A bundle holds the saved sign-in-chain cookies and the current token, nothing
else. Import merges rather than replaces: the newer of the two saved sets wins
per cookie, unexpired cookies only one side knows are kept, and the token is
replaced only by one that lasts longer.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import session

BUNDLE_KEY = "ufora_session_bundle"
BUNDLE_VERSION = 1
TOKEN_FILENAME = "token.json"
STDIO = "-"


class BundleError(ValueError):
    """The file is not a session bundle this version can import."""


@dataclass(frozen=True)
class ImportSummary:
    cookies_imported: int
    cookies_total: int
    token_replaced: bool
    token_expires_at: float | None


def token_file() -> Path:
    return session.state_dir() / TOKEN_FILENAME


def _read_token() -> dict[str, Any] | None:
    try:
        data = json.loads(token_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("token"), str) else None


def export_bundle(*, now: float | None = None) -> dict[str, Any]:
    current = time.time() if now is None else now
    return {
        BUNDLE_KEY: BUNDLE_VERSION,
        "exported_at": int(current),
        "session": {
            "saved_at": session.session_saved_at(),
            "cookies": session.load_session_cookies(now=current),
        },
        "token": _read_token(),
    }


def write_bundle(target: str, bundle: dict[str, Any]) -> None:
    text = json.dumps(bundle)
    if target == STDIO:
        sys.stdout.write(text + "\n")
        sys.stdout.flush()
        return
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text + "\n")


def read_bundle(source: str) -> dict[str, Any]:
    try:
        raw = sys.stdin.read() if source == STDIO else Path(source).read_text(encoding="utf-8")
        data = json.loads(raw)
    except OSError as exc:
        raise BundleError(f"cannot read {source}: {exc.strerror or exc}") from exc
    except ValueError as exc:
        raise BundleError("not a JSON session bundle") from exc
    return validate_bundle(data)


def validate_bundle(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or data.get(BUNDLE_KEY) != BUNDLE_VERSION:
        raise BundleError("not a Ufora session bundle (expected `ufora session export` output)")
    session_part = data.get("session")
    if not isinstance(session_part, dict) or not isinstance(session_part.get("cookies"), list):
        raise BundleError("bundle has no cookie list")
    token = data.get("token")
    if token is not None and not (
        isinstance(token, dict) and isinstance(token.get("token"), str) and isinstance(token.get("exp"), int)
    ):
        raise BundleError("bundle token has an unexpected shape")
    return data


def _valid_cookie(item: Any) -> bool:
    return (
        isinstance(item, dict)
        and all(isinstance(item.get(key), str) for key in ("name", "value", "domain"))
        and session.is_session_cookie_domain(item["domain"])
    )


def import_bundle(bundle: dict[str, Any], *, now: float | None = None) -> ImportSummary:
    current = time.time() if now is None else now
    incoming = [dict(item) for item in bundle["session"]["cookies"] if _valid_cookie(item)]
    incoming_saved_at = float(bundle["session"].get("saved_at") or 0)
    local_saved_at = session.session_saved_at()
    local = session.load_session_cookies(now=current)
    if incoming_saved_at >= local_saved_at:
        merged = session.merge_session_cookies(local, incoming, now=current)
    else:
        merged = session.merge_session_cookies(incoming, local, now=current)
    session.save_session_cookies(merged, saved_at=int(max(incoming_saved_at, local_saved_at, current)))

    token_replaced = _import_token(bundle.get("token"), now=current)
    token = _read_token()
    expires = float(token["exp"]) if token and isinstance(token.get("exp"), int | float) else None
    return ImportSummary(len(incoming), len(merged), token_replaced, expires)


def _import_token(token: dict[str, Any] | None, *, now: float) -> bool:
    if not token or token["exp"] <= now:
        return False
    local = _read_token()
    if local and isinstance(local.get("exp"), int | float) and local["exp"] >= token["exp"]:
        return False
    target = token_file()
    target.parent.mkdir(mode=0o700, exist_ok=True)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(token, handle, indent=2)
    return True
