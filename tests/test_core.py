from __future__ import annotations

from ufora_cli.core import _translate_upstream_text


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
