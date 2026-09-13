from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from d2l.errors import APIError

from .materials import _client_and_resolver, _course_identity, _overview_for


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _normalize_since(since: str | None) -> str | None:
    if not since:
        return None
    value = since.strip()
    if len(value) == 10 and value[4] == "-" and value[7] == "-":
        return f"{value}T00:00:00.000Z"
    return value


def _announcement_date(item: dict[str, Any]) -> str:
    return str(item.get("StartDate") or item.get("CreatedDate") or item.get("PublicationDate") or "")


def get_announcements(course: str | None = None, *, since: str | None = None) -> list[dict[str, Any]]:
    """Return actual course announcements, globally or for one course.

    Brightspace's user Activity Feed is a separate surface and can be empty even
    when courses have announcements. Ufora AI therefore aggregates the News
    endpoint across current course offerings when no course is provided.
    """
    client, resolver = _client_and_resolver()
    since_value = _normalize_since(since)
    enrollments = [resolver.resolve(course)] if course else resolver.list_courses()
    results: list[dict[str, Any]] = []

    for enrollment in enrollments:
        org = enrollment["OrgUnit"]
        items = client.news(org["Id"], since=since_value)
        if not isinstance(items, list):
            continue
        course_identity = _course_identity(org)
        for item in items:
            if not isinstance(item, dict):
                continue
            record = dict(item)
            record["Course"] = course_identity
            results.append(record)

    results.sort(key=_announcement_date, reverse=True)
    return results


def _overview_record(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if raw is None:
        return None
    description = raw.get("Description") or {}
    return {
        "description_text": description.get("Text", "") if isinstance(description, dict) else "",
        "description_html": description.get("Html", "") if isinstance(description, dict) else "",
        "has_attachment": bool(raw.get("HasAttachment")),
    }


def get_course_context(
    course: str,
    *,
    days: int = 14,
    include_content: bool = True,
    announcement_limit: int = 20,
) -> dict[str, Any]:
    """Return the high-value student-visible context for one Ufora course.

    Individual optional Brightspace surfaces are allowed to be unavailable. In
    that case the section falls back to an empty value and its API error is
    recorded in ``section_errors`` rather than discarding the rest of the course.
    Authentication failures are intentionally not swallowed by this helper.
    """
    if not course.strip():
        raise ValueError("course must not be empty")
    if not 1 <= days <= 366:
        raise ValueError("days must be between 1 and 366")
    if not 1 <= announcement_limit <= 100:
        raise ValueError("announcement_limit must be between 1 and 100")

    client, resolver = _client_and_resolver()
    enrollment = resolver.resolve(course)
    org = enrollment["OrgUnit"]
    org_id = org["Id"]
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days)
    errors: dict[str, dict[str, Any]] = {}

    def optional(section: str, fn: Callable[[], Any], default: Any) -> Any:
        try:
            return fn()
        except APIError as exc:
            errors[section] = {
                "status_code": exc.status_code,
                "message": str(exc),
            }
            return default

    overview = optional("overview", lambda: _overview_for(client, org_id), None)
    announcements = optional("announcements", lambda: client.news(org_id), [])
    grades = optional("grades", lambda: client.grades(org_id), [])
    assignments = optional("assignments", lambda: client.assignments(org_id), [])
    quizzes = optional("quizzes", lambda: client.quizzes(org_id), [])
    discussions = optional("discussions", lambda: client.discussion_forums(org_id), [])
    calendar_events = optional(
        "calendar",
        lambda: client.calendar_events(org_id=org_id, start=_iso(now), end=_iso(end)),
        [],
    )
    due = optional(
        "due",
        lambda: client.due_items(org_ids_csv=str(org_id), start=_iso(now), end=_iso(end)),
        [],
    )
    overdue = optional("overdue", lambda: client.overdue_items(org_ids_csv=str(org_id)), [])
    updates = optional("updates", lambda: client.updates(org_id=org_id), None)
    content_toc = (
        optional("content", lambda: client.content_toc(org_id), {"Modules": []})
        if include_content
        else None
    )

    return {
        "generated_at": _iso(now),
        "course": _course_identity(org),
        "access": enrollment.get("Access"),
        "overview": _overview_record(overview),
        "announcements": announcements[:announcement_limit] if isinstance(announcements, list) else [],
        "grades": grades if isinstance(grades, list) else grades,
        "assignments": assignments if isinstance(assignments, list) else [],
        "quizzes": quizzes if isinstance(quizzes, list) else [],
        "discussion_forums": discussions if isinstance(discussions, list) else [],
        "calendar_events": calendar_events if isinstance(calendar_events, list) else [],
        "due": due if isinstance(due, list) else [],
        "overdue": overdue if isinstance(overdue, list) else [],
        "updates": updates,
        "content_toc": content_toc,
        "section_errors": errors,
    }
