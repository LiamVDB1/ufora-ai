from __future__ import annotations

from types import SimpleNamespace

from d2l.errors import ForbiddenError
import pytest

from ufora_cli import course_context


class FakeResolver:
    def resolve(self, _course):
        return {
            "OrgUnit": {"Id": 42, "Code": "TEST_2026", "Name": "Test Course"},
            "Access": {"IsActive": True},
        }

    def list_courses(self):
        return [
            self.resolve("TEST"),
            {
                "OrgUnit": {"Id": 43, "Code": "OTHER_2026", "Name": "Other Course"},
                "Access": {"IsActive": True},
            },
        ]


class FakeClient:
    def news(self, org_id, since=None):
        title = "Welcome" if org_id == 42 else "Other update"
        date = "2026-09-12T10:00:00.000Z" if org_id == 42 else "2026-09-13T10:00:00.000Z"
        return [{"Title": title, "StartDate": date, "Body": {"Text": "Read the Overview first."}, "Since": since}]

    def grades(self, _org_id):
        return []

    def assignments(self, _org_id):
        return [{"Id": 1, "Name": "Project"}]

    def quizzes(self, _org_id):
        return []

    def discussion_forums(self, _org_id):
        raise ForbiddenError(403, "https://example.invalid/discussions", "")

    def calendar_events(self, **_kwargs):
        return []

    def due_items(self, **_kwargs):
        return []

    def overdue_items(self, **_kwargs):
        return []

    def updates(self, **_kwargs):
        return {"UnreadDiscussions": 0}

    def content_toc(self, _org_id):
        return {"Modules": [{"ModuleId": 1, "Title": "Project", "Description": {"Text": "Full project brief"}}]}


def test_course_context_includes_overview_and_survives_optional_section_failure(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(course_context, "_client_and_resolver", lambda: (FakeClient(), FakeResolver()))
    monkeypatch.setattr(
        course_context,
        "_overview_for",
        lambda client, org_id: {
            "Description": {"Text": "Required software, grading rules and closed-book exam."},
            "HasAttachment": False,
        },
    )

    result = course_context.get_course_context("TEST", include_content=True)

    assert "grading rules" in result["overview"]["description_text"]
    assert result["assignments"][0]["Name"] == "Project"
    assert result["content_toc"]["Modules"][0]["Title"] == "Project"
    assert result["discussion_forums"] == []
    assert result["section_errors"]["discussions"]["status_code"] == 403


def test_announcements_without_course_aggregate_real_course_news(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(course_context, "_client_and_resolver", lambda: (FakeClient(), FakeResolver()))

    result = course_context.get_announcements(since="2026-09-01")

    assert [item["Title"] for item in result] == ["Other update", "Welcome"]
    assert result[0]["Course"]["name"] == "Other Course"
    assert result[0]["Since"] == "2026-09-01T00:00:00.000Z"


def test_announcements_with_course_only_reads_that_course(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(course_context, "_client_and_resolver", lambda: (FakeClient(), FakeResolver()))

    result = course_context.get_announcements("TEST")

    assert len(result) == 1
    assert result[0]["Title"] == "Welcome"
    assert result[0]["Course"]["code"] == "TEST_2026"
