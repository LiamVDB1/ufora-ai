"""Run d2l-cli with UGent-specific compatibility fixes applied.

UGent's Brightspace instance localizes ``OrgUnit.Type.Name`` for course
offerings to ``Cursuseditie``. d2l-cli 0.2.2 filters on the English display
name ``Course Offering``, which makes every UGent course disappear and causes
calendar/due/dump to send an empty org-unit list. Brightspace also provides the
stable machine-readable ``OrgUnit.Type.Code`` field, which remains
``Course Offering`` across localizations.
"""

from __future__ import annotations

from datetime import datetime
import importlib
import re

import click
from urllib.parse import unquote

from d2l.errors import D2LError
from d2l.resolver import CourseResolver


def _is_course_offering(enrollment: dict) -> bool:
    org_type = enrollment.get("OrgUnit", {}).get("Type", {})
    return (
        org_type.get("Code") == "Course Offering"
        or org_type.get("Name") == "Course Offering"
    )


def _academic_year_start() -> int:
    """Return the UGent academic-year start year for today's date."""
    now = datetime.now()
    return now.year if now.month >= 9 else now.year - 1


def _offering_year(enrollment: dict) -> int | None:
    code = enrollment.get("OrgUnit", {}).get("Code", "") or ""
    match = re.search(r"_(20\d{2})$", code)
    return int(match.group(1)) if match else None


def _all_courses(self: CourseResolver):
    """Return real course offerings only, excluding UGent groups such as GR01."""
    return [e for e in self._load() if _is_course_offering(e)]


def _list_courses(self: CourseResolver):
    """Return this academic year's real course offerings.

    UGent leaves historical offerings marked active for years, which makes the
    generic Brightspace notion of ``active`` unusable for calendar/due queries.
    Normal UGent course offering codes end in the academic-year start year,
    e.g. ``E017950A_2026`` for academic year 2026-2027.
    """
    offerings = _all_courses(self)
    year = _academic_year_start()
    current = [e for e in offerings if _offering_year(e) == year]
    return current or offerings


def _disambiguate(self: CourseResolver, query: str, matches: list[dict]):
    courses = [match for match in matches if _is_course_offering(match)]
    if len(courses) == 1:
        return courses[0]
    if courses:
        matches = courses

    lines = [f"Multiple matches for '{query}':"]
    for index, match in enumerate(matches, 1):
        org_unit = match.get("OrgUnit", {})
        lines.append(f"  {index}. [{org_unit.get('Id')}] {org_unit.get('Name')}")
    lines.append("Be more specific or use the numeric ID.")
    raise D2LError("\n".join(lines))


def _patch_resolver() -> None:
    CourseResolver.list_courses = _list_courses
    CourseResolver.all_enrollments = _all_courses
    CourseResolver._disambiguate = _disambiguate


def _patch_dump() -> None:
    """Make --shallow actually include enrollment/course identities."""
    dump_module = importlib.import_module("d2l.commands.dump")
    original_json = dump_module._dump_json
    original_text = dump_module._dump_text

    def dump_json(me, now, courses, overdue, due_soon, client, sections, shallow, since_dt, since_iso, since_hours):
        if shallow:
            return original_json(me, now, courses, overdue, due_soon, client, set(), False, since_dt, since_iso, since_hours)
        return original_json(me, now, courses, overdue, due_soon, client, sections, shallow, since_dt, since_iso, since_hours)

    def dump_text(me, now, courses, overdue, due_soon, client, sections, shallow, fmt, since_dt, since_iso, since_hours):
        if shallow:
            return original_text(me, now, courses, overdue, due_soon, client, set(), False, fmt, since_dt, since_iso, since_hours)
        return original_text(me, now, courses, overdue, due_soon, client, sections, shallow, fmt, since_dt, since_iso, since_hours)

    dump_module._dump_json = dump_json
    dump_module._dump_text = dump_text


def _topic_label(topic: dict) -> str:
    """Return a stable human label for Brightspace content topics."""
    if topic.get("TypeIdentifier") == "File" or topic.get("TopicType") == 1:
        return "file"
    if topic.get("TypeIdentifier") in {"Link", "Url"}:
        return "link"
    return "link"


def _patch_content() -> None:
    """Render UGent file topics as files instead of mislabeled links."""
    content_module = importlib.import_module("d2l.commands.content")

    def print_tree(items, indent=0):
        prefix = "  " * indent
        for item in items:
            typ = item.get("Type", -1)
            title = item.get("Title", "?")
            if typ == 0:
                click.echo(f"{prefix}- [M] {title}")
                children = item.get("Modules", []) + item.get("Topics", [])
                if children:
                    print_tree(children, indent + 1)
            else:
                click.echo(f"{prefix}- [{_topic_label(item)}] {title}")

    def print_toc(toc, indent=0):
        if isinstance(toc, dict):
            modules = toc.get("Modules", [])
            topics = toc.get("Topics", [])
        elif isinstance(toc, list):
            modules = toc
            topics = []
        else:
            return

        prefix = "  " * indent
        for module in modules:
            title = module.get("Title", module.get("Name", "?"))
            click.echo(f"{prefix}- {title}")
            print_toc(module, indent + 1)
        for topic in topics:
            title = topic.get("Title", topic.get("Name", "?"))
            click.echo(f"{prefix}  - [{_topic_label(topic)}] {title}")

    content_module._print_tree = print_tree
    content_module._print_toc = print_toc


def _patch_download() -> None:
    """Decode URL-escaped filenames returned by Ufora download headers."""
    download_module = importlib.import_module("d2l.commands.download")
    original = download_module._filename_from_response

    def decoded_filename(response, fallback):
        return unquote(original(response, fallback))

    download_module._filename_from_response = decoded_filename


def main() -> None:
    _patch_resolver()
    _patch_dump()
    _patch_content()
    _patch_download()
    # Import after patching. Command modules construct CourseResolver at runtime,
    # so all d2l-cli commands now see the corrected UGent behavior.
    from d2l.cli import cli

    cli(prog_name="ufora")


if __name__ == "__main__":
    main()
