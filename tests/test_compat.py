from __future__ import annotations

import time
from datetime import UTC, datetime

import pytest
from d2l import auth as d2l_auth
from d2l.errors import TokenExpiredError, TokenNotFoundError

from ufora_cli import d2l_entry


class FakeResolver:
    def __init__(self, enrollments):
        self._items = enrollments

    def _load(self):
        return self._items


def enrollment(*, oid: int, code: str, name: str, type_code: str, type_name: str):
    return {
        "OrgUnit": {
            "Id": oid,
            "Code": code,
            "Name": name,
            "Type": {"Code": type_code, "Name": type_name},
        }
    }


def test_saved_token_loader_ignores_environment_token_fallback(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("D2L_TOKEN", "attacker-controlled-environment-value")
    monkeypatch.setattr(d2l_auth, "_read_token_file", lambda: None)

    with pytest.raises(TokenNotFoundError, match="ufora login"):
        d2l_entry._load_saved_token_only()


def test_saved_token_loader_accepts_only_valid_local_token(monkeypatch: pytest.MonkeyPatch):
    expires = int(time.time()) + 3600
    monkeypatch.setattr(
        d2l_auth,
        "_read_token_file",
        lambda: {"token": "local-token", "exp": expires},
    )
    monkeypatch.setattr(
        d2l_auth,
        "_parse_bearer_claims",
        lambda token: {"exp": expires} if token == "local-token" else None,
    )

    assert d2l_entry._load_saved_token_only() == "local-token"


def test_saved_token_loader_rejects_expired_local_token(monkeypatch: pytest.MonkeyPatch):
    expires = int(time.time()) - 1
    monkeypatch.setattr(
        d2l_auth,
        "_read_token_file",
        lambda: {"token": "expired-token", "exp": expires},
    )
    monkeypatch.setattr(d2l_auth, "_parse_bearer_claims", lambda _token: {"exp": expires})

    with pytest.raises(TokenExpiredError, match="ufora login"):
        d2l_entry._load_saved_token_only()


def test_ugent_localized_course_offering_is_recognized():
    item = enrollment(
        oid=1,
        code="E017950A_2026",
        name="E017950A - Secure Software and Systems",
        type_code="Course Offering",
        type_name="Cursuseditie",
    )
    assert d2l_entry._is_course_offering(item)


def test_groups_are_excluded_from_courses():
    course = enrollment(
        oid=1,
        code="C003783A_2025",
        name="C003783A - Logisch programmeren",
        type_code="Course Offering",
        type_name="Cursuseditie",
    )
    group = enrollment(
        oid=2,
        code="uuid",
        name="C003783A GR01",
        type_code="Group",
        type_name="Groep",
    )
    assert d2l_entry._all_courses(FakeResolver([course, group])) == [course]


def test_academic_year_boundary_uses_brussels_local_date():
    # 22:30 UTC on Aug 31 is already Sep 1 in Belgium (CEST).
    assert d2l_entry._academic_year_start(datetime(2026, 8, 31, 22, 30, tzinfo=UTC)) == 2026


def test_current_courses_use_academic_year_suffix(monkeypatch):
    monkeypatch.setattr(d2l_entry, "_academic_year_start", lambda: 2026)
    old = enrollment(
        oid=1,
        code="C003783A_2025",
        name="Old",
        type_code="Course Offering",
        type_name="Cursuseditie",
    )
    current = enrollment(
        oid=2,
        code="E017950A_2026",
        name="Current",
        type_code="Course Offering",
        type_name="Cursuseditie",
    )
    assert d2l_entry._list_courses(FakeResolver([old, current])) == [current]


def test_current_courses_do_not_silently_fall_back_to_history(monkeypatch):
    monkeypatch.setattr(d2l_entry, "_academic_year_start", lambda: 2026)
    old = enrollment(
        oid=1,
        code="C003783A_2025",
        name="Old",
        type_code="Course Offering",
        type_name="Cursuseditie",
    )

    assert d2l_entry._list_courses(FakeResolver([old])) == []


def test_doctor_hides_upstream_only_features_and_returns_valid_ufora_steps():
    checks = [
        {"check": "cli", "ok": True, "detail": "d2l-cli 0.2.2", "next_step": None, "info_only": False},
        {
            "check": "token",
            "ok": False,
            "detail": "D2L token expired",
            "next_step": "d2l login",
            "info_only": False,
        },
        {
            "check": "syllabus",
            "ok": True,
            "detail": "SimpleSyllabus not configured",
            "next_step": None,
            "info_only": True,
        },
        {
            "check": "onboarding",
            "ok": False,
            "detail": "Not onboarded",
            "next_step": "d2l onboard",
            "info_only": True,
        },
    ]

    cleaned = d2l_entry._clean_doctor_checks(checks)

    assert [item["check"] for item in cleaned] == ["cli", "token"]
    assert cleaned[0]["detail"].startswith("Ufora AI ")
    assert cleaned[1]["detail"] == "Ufora token expired"
    assert cleaned[1]["next_step"] == "ufora login"
    assert "d2l" not in str(cleaned).lower()
    assert "ufora onboard" not in str(cleaned).lower()


def test_file_topics_are_labeled_as_files_even_without_topictype():
    topic = {"TypeIdentifier": "File", "Title": "Hoofdstuk 1"}
    assert d2l_entry._topic_label(topic) == "file"


def test_external_topics_are_labeled_as_links():
    topic = {"TypeIdentifier": "Link", "Title": "Dodona"}
    assert d2l_entry._topic_label(topic) == "link"


def test_internal_child_cli_removes_unneeded_write_or_maintenance_commands():
    class FakeCli:
        def __init__(self):
            self.commands = {
                "courses": object(),
                "login": object(),
                "download": object(),
                "download-content": object(),
                "onboard": object(),
                "setup": object(),
                "skill": object(),
                "syllabus": object(),
                "update": object(),
            }

    cli = FakeCli()
    d2l_entry._strip_internal_commands(cli)

    assert set(cli.commands) == {"courses", "login"}


def test_disambiguation_prefers_course_over_gr01():
    course = enrollment(
        oid=1,
        code="C003783A_2025",
        name="C003783A - Logisch programmeren",
        type_code="Course Offering",
        type_name="Cursuseditie",
    )
    group = enrollment(
        oid=2,
        code="uuid",
        name="C003783A GR01",
        type_code="Group",
        type_name="Groep",
    )
    assert d2l_entry._disambiguate(FakeResolver([]), "C003783A", [course, group]) == course
