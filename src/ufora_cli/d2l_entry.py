"""Run d2l-cli with UGent-specific compatibility fixes applied.

UGent's Brightspace instance localizes ``OrgUnit.Type.Name`` for course
offerings to ``Cursuseditie``. d2l-cli 0.2.2 filters on the English display
name ``Course Offering``, which makes every UGent course disappear and causes
calendar/due/dump to send an empty org-unit list. Brightspace also provides the
stable machine-readable ``OrgUnit.Type.Code`` field, which remains
``Course Offering`` across localizations.
"""

from __future__ import annotations

import importlib
import re
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import click
from d2l import auth as d2l_auth
from d2l.errors import D2LError, TokenExpiredError, TokenNotFoundError
from d2l.resolver import CourseResolver

from . import __version__, renewal, session
from .core import _translate_upstream_text


def _is_course_offering(enrollment: dict) -> bool:
    org_type = enrollment.get("OrgUnit", {}).get("Type", {})
    return (
        org_type.get("Code") == "Course Offering"
        or org_type.get("Name") == "Course Offering"
    )


UGENT_TIMEZONE = ZoneInfo("Europe/Brussels")


def _load_saved_token_only() -> str:
    """Load only Ufora's fixed local token file; never inherit cwd/env credentials."""
    data = d2l_auth._read_token_file()
    if not isinstance(data, dict):
        raise TokenNotFoundError("No saved Ufora token found. Run: ufora login")

    token = data.get("token")
    claims = d2l_auth._parse_bearer_claims(token)
    if not claims:
        raise TokenNotFoundError("Saved Ufora token is invalid. Run: ufora login")

    exp = claims.get("exp", data.get("exp", 0))
    if not isinstance(exp, int | float) or exp <= time.time():
        raise TokenExpiredError("Saved Ufora token is expired. Run: ufora login")
    return token


def _patch_auth_sources() -> None:
    """Keep Ufora authentication scoped to ~/.d2l rather than cwd/.env/process env."""
    d2l_auth.load_token = _load_saved_token_only
    loaded_cli = sys.modules.get("d2l.cli")
    if loaded_cli is not None:
        loaded_cli.load_token = _load_saved_token_only


def _patch_session() -> None:
    """Carry the SSO session across headless launches and never capture near-expiry tokens."""
    auth_cmd = importlib.import_module("d2l.commands.auth_cmd")
    auth_cmd._launch_context = session.wrap_launch_context(auth_cmd._launch_context)
    auth_cmd._parse_token = session.require_min_lifetime(auth_cmd._parse_token)
    # Headless captures (this CLI's refresh, upstream's automatic re-login) must
    # click through UGent's landing page and Microsoft's account picker.
    auth_cmd._capture_and_save = renewal.wrap_capture_and_save(auth_cmd._capture_and_save)


@click.command(name="refresh")
@click.option("--debug", is_flag=True, help="Trace the sign-in chain and save screenshots under ~/.d2l/debug/.")
def refresh(debug: bool) -> None:
    """Renew the token from the saved sign-in without opening a visible browser."""
    diagnostics = renewal.Diagnostics.from_flags(debug)
    result = renewal.renew_headless(diagnostics=diagnostics)
    if diagnostics.enabled:
        click.echo(f"Diagnostics saved under {diagnostics.directory}", err=True)
    if not result.ok:
        click.echo(renewal.failure_message(result), err=True)
        raise SystemExit(1)
    info = d2l_auth.token_info()
    click.echo(f"Ufora token renewed; valid until {info.get('expires_at')}.")


def _academic_year_start(now: datetime | None = None) -> int:
    """Return the UGent academic-year start year using the Brussels local date."""
    local_now = (now or datetime.now(UGENT_TIMEZONE)).astimezone(UGENT_TIMEZONE)
    return local_now.year if local_now.month >= 9 else local_now.year - 1


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
    return [e for e in offerings if _offering_year(e) == year]


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


def _clean_doctor_checks(checks: list[dict]) -> list[dict]:
    """Remove upstream-only diagnostics and expose only valid Ufora recovery steps."""
    cleaned: list[dict] = []
    for raw in checks:
        if raw.get("check") in {"syllabus", "onboarding"}:
            continue

        check = dict(raw)
        if check.get("check") == "cli":
            check["detail"] = f"Ufora AI {__version__}"
        else:
            check["detail"] = _translate_upstream_text(str(check.get("detail") or ""))
        if check.get("check") == "courses" and check.get("ok"):
            check["detail"] = str(check["detail"]).replace("active course(s)", "current course(s)")

        next_step = check.get("next_step")
        if next_step:
            check["next_step"] = _translate_upstream_text(str(next_step))
        cleaned.append(check)
    return cleaned


def _patch_doctor() -> None:
    """Keep upstream doctor useful without leaking unsupported d2l-cli features."""
    doctor_module = importlib.import_module("d2l.commands.doctor")
    original_run_checks = doctor_module._run_checks

    def run_checks():
        return _clean_doctor_checks(original_run_checks())

    doctor_module._run_checks = run_checks


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


def _strip_internal_commands(cli_group: click.Group) -> None:
    """Remove upstream commands that Ufora AI does not expose or need internally."""
    for name in (
        "download",
        "download-content",
        "onboard",
        "setup",
        "skill",
        "syllabus",
        "update",
    ):
        cli_group.commands.pop(name, None)


def main() -> None:
    _patch_auth_sources()
    _patch_session()
    _patch_resolver()
    _patch_doctor()
    _patch_dump()
    _patch_content()
    # Import after patching. Command modules construct CourseResolver at runtime,
    # so all d2l-cli commands now see the corrected UGent behavior.
    from d2l.cli import cli

    _strip_internal_commands(cli)
    cli.add_command(refresh)
    cli(prog_name="ufora")


if __name__ == "__main__":
    main()
