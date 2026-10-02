from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

UFORA_HOST = "https://ufora.ugent.be"
DEFAULT_TIMEOUT_SECONDS = 90
D2L_STATE_DIRNAME = ".d2l"
GRAPHICAL_ENV_KEYS = (
    "DISPLAY",
    "WAYLAND_DISPLAY",
    "XAUTHORITY",
    "XDG_RUNTIME_DIR",
    "XDG_SESSION_TYPE",
)
CHROMIUM_LOCK_NAMES = ("SingletonLock", "SingletonCookie", "SingletonSocket")
NATIVE_WINDOW_PLATFORMS = ("darwin", "win32")


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


def has_graphical_session(
    env: Mapping[str, str] | None = None,
    *,
    platform: str | None = None,
) -> bool:
    """True when the environment can launch a headed Chromium window.

    On Linux that requires an X11 or Wayland display. macOS and Windows have no
    such variables: a local session can always open a window, while an SSH
    session can only do so through a forwarded X display (e.g. XQuartz).
    """
    current = env if env is not None else os.environ
    if current.get("DISPLAY") or current.get("WAYLAND_DISPLAY"):
        return True
    return _has_native_window_server(platform) and not is_ssh_session(current)


def _has_native_window_server(platform: str | None = None) -> bool:
    """True on platforms whose desktop is not exposed through DISPLAY/Wayland."""
    return (platform if platform is not None else sys.platform) in NATIVE_WINDOW_PLATFORMS


def is_ssh_session(env: Mapping[str, str] | None = None) -> bool:
    """True when this process is an SSH login without a local desktop."""
    current = env if env is not None else os.environ
    return bool(
        current.get("SSH_CONNECTION") or current.get("SSH_CLIENT") or current.get("SSH_TTY")
    )


def discover_graphical_session(*, uid: int | None = None) -> dict[str, str]:
    """Best-effort display variables from the caller's live graphical session.

    Hermes and SSH terminals often have no DISPLAY even when the same user has
    an active GNOME/Wayland session on the machine. Playwright then launches
    Chromium, the process exits immediately, and upstream d2l-cli only prints
    the first line: "Target page, context or browser has been closed".
    """
    user_id = os.getuid() if uid is None else uid
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{user_id}")
    found: dict[str, str] = {}
    if runtime.is_dir():
        found["XDG_RUNTIME_DIR"] = str(runtime)
        sockets = [
            path
            for path in sorted(runtime.glob("wayland-[0-9]*"))
            if not path.name.endswith(".lock") and _is_socket(path)
        ]
        if sockets:
            found["WAYLAND_DISPLAY"] = sockets[0].name
            found.setdefault("XDG_SESSION_TYPE", "wayland")
        auths = sorted(runtime.glob(".mutter-Xwaylandauth.*"))
        if auths:
            found["XAUTHORITY"] = str(auths[-1])

    display, auth = _xwayland_display(user_id)
    if display:
        found["DISPLAY"] = display
    if auth and "XAUTHORITY" not in found:
        found["XAUTHORITY"] = auth
    return {key: value for key, value in found.items() if value}


def inherit_graphical_session(
    env: Mapping[str, str],
    *,
    discovered: Mapping[str, str] | None = None,
    platform: str | None = None,
) -> dict[str, str]:
    """Copy a live graphical session into env when DISPLAY/Wayland are missing.

    Discovery reads Linux X11/Wayland state, so it is skipped on macOS and
    Windows, where a missing display cannot be recovered from the environment.
    """
    merged = dict(env)
    if has_graphical_session(merged, platform=platform):
        return merged
    if discovered is None and _has_native_window_server(platform):
        return merged
    session = dict(discovered) if discovered is not None else discover_graphical_session()
    for key in GRAPHICAL_ENV_KEYS:
        value = session.get(key)
        if value and not merged.get(key):
            merged[key] = value
    return merged


def clear_stale_chromium_locks(profile: Path) -> bool:
    """Remove Chrome singleton files left behind by a crashed login browser."""
    lock = profile / "SingletonLock"
    if not lock.exists() and not lock.is_symlink():
        return False
    pid = _singleton_lock_pid(lock)
    if pid is not None and _pid_is_alive(pid):
        return False
    removed = False
    for name in CHROMIUM_LOCK_NAMES:
        path = profile / name
        try:
            path.unlink()
            removed = True
        except FileNotFoundError:
            continue
        except OSError:
            continue
    return removed


def _is_socket(path: Path) -> bool:
    try:
        return path.is_socket()
    except OSError:
        return False


def _pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _singleton_lock_pid(lock: Path) -> int | None:
    try:
        target = os.readlink(lock) if lock.is_symlink() else lock.read_text(encoding="utf-8")
    except OSError:
        return None
    suffix = target.rsplit("-", 1)[-1].strip()
    return int(suffix) if suffix.isdigit() else None


def _xwayland_display(uid: int) -> tuple[str | None, str | None]:
    proc_root = Path("/proc")
    if not proc_root.is_dir():
        return None, None
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            status = (entry / "status").read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        uid_line = next((line for line in status.splitlines() if line.startswith("Uid:")), "")
        uid_parts = uid_line.split()
        if len(uid_parts) < 2 or uid_parts[1] != str(uid):
            continue
        try:
            cmdline = (entry / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        args = [part.decode("utf-8", "replace") for part in cmdline if part]
        if not args:
            continue
        if Path(args[0]).name != "Xwayland":
            continue
        display = next((arg for arg in args[1:] if arg.startswith(":") and arg[1:].isdigit()), None)
        auth = None
        if "-auth" in args:
            index = args.index("-auth")
            if index + 1 < len(args):
                auth = args[index + 1]
                if f"/run/user/{uid}/" not in auth.replace("\\", "/"):
                    continue
        return display, auth
    return None, None


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
        for name in ("token.json", "session.json"):
            secret_file = state_dir / name
            if secret_file.exists():
                secret_file.chmod(0o600)
    except OSError:
        return


def clear_auth_state() -> list[str]:
    """Remove Ufora's locally cached token, saved sign-in cookies and browser profile.

    This is deliberately limited to the fixed ``~/.d2l`` credential paths used
    by the pinned login flow. It does not claim to revoke a token server-side;
    it only removes the local copies/session material from this machine.
    """
    state_dir = Path.home() / D2L_STATE_DIRNAME
    removed: list[str] = []
    browser_profile = state_dir / "browser_profile"

    try:
        for name in ("token.json", "session.json"):
            secret_file = state_dir / name
            if secret_file.exists() or secret_file.is_symlink():
                secret_file.unlink()
                removed.append(name)

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


def run_d2l_passthrough(
    args: Iterable[str],
    *,
    interactive: bool = False,
    env: Mapping[str, str] | None = None,
) -> int:
    """Run the internal Brightspace command while preserving the Ufora abstraction."""
    harden_d2l_state()
    command = [*_d2l_command(), *list(args)]
    child_env = ufora_env(dict(env) if env is not None else None)
    if interactive:
        completed = subprocess.run(command, env=child_env, check=False)
        return completed.returncode

    completed = subprocess.run(
        command,
        env=child_env,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.stdout:
        sys.stdout.write(sanitize_untrusted_text(_translate_upstream_text(completed.stdout)))
    if completed.stderr:
        sys.stderr.write(sanitize_untrusted_text(_translate_upstream_text(completed.stderr)))
    return completed.returncode


def run_d2l_captured(
    args: Iterable[str], *, timeout: int = DEFAULT_TIMEOUT_SECONDS
) -> tuple[int, str, str]:
    """Run the internal Brightspace command without echoing it.

    Returns the exit code plus sanitized stdout and stderr, so the caller decides
    what the user sees. A timeout is reported as a failure, never raised.
    """
    harden_d2l_state()
    command = [*_d2l_command(), *list(args)]
    try:
        completed = subprocess.run(
            command,
            env=ufora_env(),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return 1, "", f"timed out after {timeout} seconds"
    finally:
        harden_d2l_state()
    return (
        completed.returncode,
        sanitize_untrusted_text(_translate_upstream_text(completed.stdout or "")),
        sanitize_untrusted_text(_translate_upstream_text(completed.stderr or "")),
    )


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
