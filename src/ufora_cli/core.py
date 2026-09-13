from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

UFORA_HOST = "https://ufora.ugent.be"
DEFAULT_TIMEOUT_SECONDS = 90
D2L_STATE_DIRNAME = ".d2l"


class UforaError(RuntimeError):
    """Base exception for Ufora CLI/MCP failures."""


class UpstreamCommandError(UforaError):
    """Raised when the internal Brightspace command layer exits unsuccessfully."""

    def __init__(self, message: str, *, returncode: int | None = None) -> None:
        super().__init__(message)
        self.returncode = returncode


def _d2l_command() -> list[str]:
    """Return the internal Brightspace compatibility command."""
    return [sys.executable, "-m", "ufora_cli.d2l_entry"]


def ufora_env(base: dict[str, str] | None = None) -> dict[str, str]:
    """Return an environment forcing the Brightspace client to use UGent Ufora."""
    env = dict(base or os.environ)
    env["D2L_HOST"] = UFORA_HOST
    env.pop("D2L_TOKEN", None)
    return env


def harden_d2l_state(*, create: bool = False) -> None:
    """Best-effort permission hardening for local Ufora authentication state.

    The saved browser profile contains authenticated cookies, so protecting the
    top-level directory prevents other local users from traversing into it on
    normal POSIX filesystems. Failures are intentionally non-fatal on platforms
    where chmod semantics differ.
    """
    state_dir = Path.home() / D2L_STATE_DIRNAME
    try:
        if create:
            state_dir.mkdir(mode=0o700, exist_ok=True)
        if not state_dir.exists():
            return
        state_dir.chmod(0o700)
        token_file = state_dir / "token.json"
        if token_file.exists():
            token_file.chmod(0o600)
    except OSError:
        return


def clear_auth_state() -> list[str]:
    """Remove Ufora's locally cached token and dedicated browser profile.

    This is deliberately limited to the fixed ``~/.d2l`` credential paths used
    by the pinned login flow. It does not claim to revoke a token server-side;
    it only removes the local copies/session material from this machine.
    """
    state_dir = Path.home() / D2L_STATE_DIRNAME
    removed: list[str] = []
    token_file = state_dir / "token.json"
    browser_profile = state_dir / "browser_profile"

    try:
        if token_file.exists() or token_file.is_symlink():
            token_file.unlink()
            removed.append("token.json")

        if browser_profile.is_symlink():
            browser_profile.unlink()
            removed.append("browser_profile")
        elif browser_profile.exists():
            shutil.rmtree(browser_profile)
            removed.append("browser_profile")

        if state_dir.exists():
            state_dir.chmod(0o700)
    except OSError as exc:
        raise UforaError(
            "Could not fully remove the local Ufora authentication state. "
            f"Check {state_dir} manually: {sanitize_untrusted_text(str(exc))}"
        ) from exc

    return removed


def sanitize_untrusted_text(text: str) -> str:
    """Remove terminal-control bytes from externally controlled Ufora text."""
    return "".join(
        char
        for char in text
        if char in {"\n", "\t"} or (ord(char) >= 32 and not 127 <= ord(char) < 160)
    )


def sanitize_untrusted_data(value: Any) -> Any:
    """Recursively strip terminal-control characters from structured API data."""
    if isinstance(value, str):
        return sanitize_untrusted_text(value)
    if isinstance(value, list):
        return [sanitize_untrusted_data(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_untrusted_data(item) for item in value)
    if isinstance(value, dict):
        return {
            sanitize_untrusted_text(key) if isinstance(key, str) else key: sanitize_untrusted_data(item)
            for key, item in value.items()
        }
    return value


def _translate_upstream_text(text: str) -> str:
    """Keep internal dependency names/commands out of the public Ufora interface."""
    replacements = {
        "[*] D2L token expired — refreshing sign-in in the background...": "[*] Ufora session expired — trying the saved sign-in in the background...",
        "d2l login": "ufora login",
        "d2l courses": "ufora courses",
        "d2l setup": "ufora setup",
        "d2l doctor": "ufora doctor",
        "d2l token": "ufora token",
        "d2l-cli": "Ufora AI's Brightspace layer",
        "D2L session": "Ufora session",
        "D2L bearer token": "Ufora bearer token",
        "D2L token": "Ufora token",
        "D2L": "Ufora",
        "d2l ": "ufora ",
    }
    translated = text
    for old, new in replacements.items():
        translated = translated.replace(old, new)
    return translated


def _clean_error_text(text: str, *, limit: int = 4000) -> str:
    """Keep surfaced child-process errors concise and Ufora-branded."""
    compact = sanitize_untrusted_text(_translate_upstream_text(text.strip()))
    if len(compact) <= limit:
        return compact
    return f"{compact[:limit]}\n… (truncated)"


def run_d2l_passthrough(args: Iterable[str], *, interactive: bool = False) -> int:
    """Run the internal Brightspace command while preserving the Ufora abstraction."""
    harden_d2l_state()
    command = [*_d2l_command(), *list(args)]
    if interactive:
        completed = subprocess.run(command, env=ufora_env(), check=False)
        return completed.returncode

    completed = subprocess.run(
        command,
        env=ufora_env(),
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.stdout:
        sys.stdout.write(sanitize_untrusted_text(_translate_upstream_text(completed.stdout)))
    if completed.stderr:
        sys.stderr.write(sanitize_untrusted_text(_translate_upstream_text(completed.stderr)))
    return completed.returncode


def run_d2l_json(
    args: Iterable[str], *, timeout: int = DEFAULT_TIMEOUT_SECONDS
) -> Any:
    """Run a read-only Brightspace command and decode its JSON output.

    MCP tools call this helper so every invocation is forced to the Ufora host.
    The child process is launched without a shell, so user-provided course names
    or dates cannot become shell syntax.
    """
    harden_d2l_state()
    command = [*_d2l_command(), "--json", *list(args)]
    try:
        completed = subprocess.run(
            command,
            env=ufora_env(),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise UpstreamCommandError(
            f"Ufora request timed out after {timeout} seconds."
        ) from exc

    if completed.returncode != 0:
        detail = _clean_error_text(completed.stderr or completed.stdout)
        if not detail:
            detail = "Ufora's Brightspace layer returned an error without details."
        raise UpstreamCommandError(detail, returncode=completed.returncode)

    payload = completed.stdout.strip()
    if not payload:
        return None

    try:
        return sanitize_untrusted_data(json.loads(payload))
    except json.JSONDecodeError as exc:
        snippet = _clean_error_text(payload, limit=1000)
        raise UpstreamCommandError(
            f"Ufora returned non-JSON output while JSON was requested: {snippet}"
        ) from exc
