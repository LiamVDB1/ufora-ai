from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from collections.abc import Iterable

import click

from . import __version__
from .core import UFORA_HOST, harden_d2l_state, run_d2l_json, run_d2l_passthrough


def _run(ctx: click.Context, args: Iterable[str], *, interactive: bool = False) -> None:
    command = list(args)
    harden_d2l_state(create=interactive and bool(command) and command[0] == "login")
    if not interactive:
        output_format = (ctx.obj or {}).get("output_format")
        if output_format:
            command.insert(0, f"--{output_format}")

    try:
        code = run_d2l_passthrough(command, interactive=interactive)
    finally:
        harden_d2l_state()
    if code:
        raise SystemExit(code)


def _append_option(args: list[str], name: str, value: object | None) -> None:
    if value is not None:
        args.extend([name, str(value)])


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(version=__version__)
@click.option("--json", "output_format", flag_value="json", help="Machine-readable JSON output.")
@click.option("--md", "output_format", flag_value="md", help="Markdown output optimized for AI agents.")
@click.pass_context
def cli(ctx: click.Context, output_format: str | None) -> None:
    """Read-only CLI for UGent Ufora.

    Ufora is UGent's Brightspace learning environment. Ufora AI connects
    read-only to https://ufora.ugent.be.
    """
    ctx.ensure_object(dict)
    ctx.obj["output_format"] = output_format


@cli.command()
@click.pass_context
def setup(ctx: click.Context) -> None:
    """Check the local installation and show the next setup step."""
    click.echo(f"Ufora host: {UFORA_HOST}", err=True)
    _run(ctx, ["doctor"])


@cli.command()
@click.option("--headless", is_flag=True, help="Use a headless browser (mainly for a server with saved SSO cookies).")
@click.option(
    "--channel",
    type=click.Choice(["auto", "chromium", "chrome", "msedge"]),
    default="auto",
    show_default=True,
)
@click.pass_context
def login(ctx: click.Context, headless: bool, channel: str) -> None:
    """Open a browser and sign in with your normal UGent SSO account."""
    args = ["login", "--channel", channel]
    if headless:
        args.append("--headless")
    _run(ctx, args, interactive=True)


@cli.command()
@click.pass_context
def doctor(ctx: click.Context) -> None:
    """Diagnose host, authentication, and API access."""
    _run(ctx, ["doctor"])


@cli.command()
@click.pass_context
def token(ctx: click.Context) -> None:
    """Show the saved Brightspace token status without printing the token."""
    _run(ctx, ["token"])


@cli.command()
@click.pass_context
def whoami(ctx: click.Context) -> None:
    """Show the currently authenticated Ufora user."""
    _run(ctx, ["whoami"])


def _course_matches(enrollment: dict, query: str) -> bool:
    org = enrollment.get("OrgUnit", {})
    needle = query.casefold().strip()
    if not needle:
        return True
    haystacks = [str(org.get("Name") or ""), str(org.get("Code") or ""), str(org.get("Id") or "")]
    return any(needle in value.casefold() for value in haystacks)


def _print_courses(data: list[dict], *, output_format: str | None) -> None:
    if output_format == "json":
        click.echo(json.dumps(data, indent=2, ensure_ascii=False))
        return
    if output_format == "md":
        click.echo("| ID | Name | Code | Active |")
        click.echo("| --- | --- | --- | --- |")
        for enrollment in data:
            org = enrollment.get("OrgUnit", {})
            access = enrollment.get("Access", {})
            click.echo(
                f"| {org.get('Id', '')} | {org.get('Name', '')} | {org.get('Code', '')} | {access.get('IsActive', '')} |"
            )
        return

    click.echo("=== My Courses ===")
    if not data:
        click.echo("  (none)")
        return
    rows = []
    for enrollment in data:
        org = enrollment.get("OrgUnit", {})
        access = enrollment.get("Access", {})
        rows.append(
            (
                str(org.get("Id", "")),
                str(org.get("Name", "")),
                str(org.get("Code", "")),
                str(access.get("IsActive", "")),
            )
        )
    widths = [max(len(row[index]) for row in rows + [("ID", "Name", "Code", "Active")]) for index in range(4)]
    headers = ("ID", "Name", "Code", "Active")
    click.echo("  " + "  ".join(headers[i].ljust(widths[i]) for i in range(4)))
    click.echo("  " + "  ".join("-" * widths[i] for i in range(4)))
    for row in rows:
        click.echo("  " + "  ".join(row[i].ljust(widths[i]) for i in range(4)))


@cli.command()
@click.argument("query", required=False)
@click.option("--all", "include_all", is_flag=True, help="Include historical course offerings.")
@click.pass_context
def courses(ctx: click.Context, query: str | None, include_all: bool) -> None:
    """List courses, or find a course by name/code/ID.

    With QUERY, searches all real course offerings so older courses such as
    `ufora courses Logisch` are discoverable without first listing everything.
    """
    if not query:
        args = ["courses"]
        if include_all:
            args.append("--all")
        _run(ctx, args)
        return

    try:
        data = run_d2l_json(["courses", "--all"])
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    enrollments = data if isinstance(data, list) else []
    matches = [item for item in enrollments if _course_matches(item, query)]
    if not matches:
        raise click.ClickException(
            f"No course matching '{query}'. Try a course code, part of the title, or `ufora courses --all`."
        )
    _print_courses(matches, output_format=(ctx.obj or {}).get("output_format"))


@cli.command()
@click.argument("course", required=False)
@click.option("--final", "show_final", is_flag=True, help="Show final grades across all courses.")
@click.pass_context
def grades(ctx: click.Context, course: str | None, show_final: bool) -> None:
    """Show grades for COURSE, or use --final for all final grades."""
    if not course and not show_final:
        raise click.UsageError("Provide COURSE or use --final.")
    args = ["grades"]
    if course:
        args.append(course)
    if show_final:
        args.append("--final")
    _run(ctx, args)


@cli.command()
@click.argument("course")
@click.pass_context
def assignments(ctx: click.Context, course: str) -> None:
    """List assignments and due dates for COURSE."""
    _run(ctx, ["assignments", course])


@cli.command()
@click.argument("course")
@click.pass_context
def quizzes(ctx: click.Context, course: str) -> None:
    """List quizzes and dates for COURSE."""
    _run(ctx, ["quizzes", course])


@cli.command()
@click.argument("course")
@click.pass_context
def overview(ctx: click.Context, course: str) -> None:
    """Show the dedicated Ufora Course Overview for COURSE."""
    from .materials import get_course_overview

    try:
        data = get_course_overview(course)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    output_format = (ctx.obj or {}).get("output_format")
    if output_format == "json":
        click.echo(json.dumps(data, indent=2, ensure_ascii=False))
        return

    click.echo(f"=== Overview: {data['course'].get('name')} ===")
    course_overview = data.get("overview")
    if not course_overview:
        click.echo("  (no course overview published)")
        return
    text = (course_overview.get("description_text") or "").strip()
    click.echo(text or "  (overview exists but has no text)")
    if course_overview.get("has_attachment"):
        click.echo("\n[overview also has an attachment; use `ufora material COURSE overview` to read it when supported]")


@cli.command()
@click.argument("course")
@click.option("--days", type=click.IntRange(1, 366), default=14, show_default=True)
@click.option("--no-content", is_flag=True, help="Skip the potentially large nested content tree.")
@click.option("--announcement-limit", type=click.IntRange(1, 100), default=20, show_default=True)
@click.pass_context
def context(
    ctx: click.Context,
    course: str,
    days: int,
    no_content: bool,
    announcement_limit: int,
) -> None:
    """Return a high-value overview of one course for humans or AI agents."""
    from .course_context import get_course_context

    try:
        data = get_course_context(
            course,
            days=days,
            include_content=not no_content,
            announcement_limit=announcement_limit,
        )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    output_format = (ctx.obj or {}).get("output_format")
    if output_format == "json":
        click.echo(json.dumps(data, indent=2, ensure_ascii=False))
        return

    click.echo(f"=== Course context: {data['course'].get('name')} ===")
    overview_data = data.get("overview") or {}
    overview_text = (overview_data.get("description_text") or "").strip()
    if overview_text:
        click.echo(f"\nOverview:\n{overview_text}")
    click.echo(f"\nAnnouncements: {len(data.get('announcements') or [])}")
    click.echo(f"Grades: {len(data.get('grades') or []) if isinstance(data.get('grades'), list) else 'available'}")
    click.echo(f"Assignments: {len(data.get('assignments') or [])}")
    click.echo(f"Quizzes: {len(data.get('quizzes') or [])}")
    click.echo(f"Discussion forums: {len(data.get('discussion_forums') or [])}")
    click.echo(f"Calendar events ({days}d): {len(data.get('calendar_events') or [])}")
    click.echo(f"Due ({days}d): {len(data.get('due') or [])}")
    click.echo(f"Overdue: {len(data.get('overdue') or [])}")
    if data.get("section_errors"):
        click.echo("\nSome optional Ufora sections were unavailable; use --json for details.")


@cli.command(name="content")
@click.argument("course")
@click.option("--toc", is_flag=True, help="Return the full table of contents when supported.")
@click.pass_context
def course_content(ctx: click.Context, course: str, toc: bool) -> None:
    """Show modules and topics for COURSE."""
    args = ["content", course]
    if toc:
        args.append("--toc")
    _run(ctx, args)


@cli.command()
@click.argument("course")
@click.argument("query")
@click.option("--limit", type=click.IntRange(1, 100), default=20, show_default=True)
@click.pass_context
def search(ctx: click.Context, course: str, query: str, limit: int) -> None:
    """Search the course overview, module bodies, topics, and descriptions."""
    from .materials import search_course_content

    try:
        data = search_course_content(course, query, limit=limit)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    output_format = (ctx.obj or {}).get("output_format")
    if output_format == "json":
        click.echo(json.dumps(data, indent=2, ensure_ascii=False))
        return

    click.echo(f"=== Search: {data['course'].get('name')} ===")
    click.echo(f"Query: {query}")
    matches = data.get("matches", [])
    if not matches:
        click.echo("  (no matching Ufora content)")
        return
    for match in matches:
        path = " / ".join(match.get("module_path") or [])
        where = f"{path} / " if path else ""
        identifier = match.get("item_id") if match.get("item_id") is not None else match.get("kind")
        click.echo(f"  [{identifier}] {where}{match.get('title')} ({match.get('kind')}: {match.get('type')})")
        description = (match.get("description_text") or "").strip().replace("\n", " ")
        if description:
            click.echo(f"      {description[:240]}{'…' if len(description) > 240 else ''}")


@cli.command()
@click.argument("course")
@click.argument("material")
@click.option("--max-chars", type=click.IntRange(1000, 500000), default=60000, show_default=True)
@click.pass_context
def material(ctx: click.Context, course: str, material: str, max_chars: int) -> None:
    """Read an Overview, module body, topic, or PDF/text course material."""
    from .materials import read_material

    try:
        data = read_material(course, material, max_chars=max_chars)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    output_format = (ctx.obj or {}).get("output_format")
    if output_format == "json":
        click.echo(json.dumps(data, indent=2, ensure_ascii=False))
        return

    item = data.get("item") or data.get("topic") or {}
    content = data.get("content", {})
    click.echo(f"=== Material: {item.get('title')} ===")
    click.echo(f"Course: {data['course'].get('name')}")
    click.echo(f"Kind: {item.get('kind', 'topic')}")
    if data.get("module_path"):
        click.echo(f"Module: {' / '.join(data['module_path'])}")
    if item.get("description_text"):
        click.echo(f"\nDescription:\n{item['description_text'].strip()}")
    if content.get("filename"):
        click.echo(f"\nFile: {content['filename']} ({content.get('kind')}, {content.get('size_bytes')} bytes)")
    if content.get("text"):
        click.echo(f"\nContent:\n{content['text']}")
        if content.get("truncated"):
            click.echo("\n[truncated; increase --max-chars to read more]")
    elif content.get("source_url"):
        click.echo(f"\nURL: {content['source_url']}")
    elif content.get("note"):
        click.echo(f"\n{content['note']}")
    children = data.get("children") or []
    if children:
        click.echo("\nContains:")
        for child in children:
            click.echo(
                f"  [{child.get('id')}] {child.get('title')} ({child.get('kind')}: {child.get('type')})"
            )
    elif item.get("kind") == "module" and not (content.get("text") or "").strip():
        click.echo("\nThis module has no inline description or child materials.")
    attachment = data.get("attachment")
    if attachment:
        click.echo(f"\nAttachment: {attachment.get('filename')} ({attachment.get('kind')}, {attachment.get('size_bytes')} bytes)")
        if attachment.get("text"):
            click.echo(f"\nAttachment content:\n{attachment['text']}")
            if attachment.get("truncated"):
                click.echo("\n[attachment truncated; increase --max-chars to read more]")


@cli.command()
@click.argument("course")
@click.pass_context
def discussions(ctx: click.Context, course: str) -> None:
    """Show discussion forums, topics, and posts for COURSE."""
    _run(ctx, ["discussions", course])


@cli.command()
@click.argument("course", required=False)
@click.option("--since", help="Only announcements since YYYY-MM-DD or an ISO date/time.")
@click.pass_context
def news(ctx: click.Context, course: str | None, since: str | None) -> None:
    """Show actual course announcements.

    Without COURSE, aggregates announcements across current academic-year
    courses. This is intentionally different from Brightspace's separate
    Activity Feed, which may be empty even when courses have announcements.
    """
    from .course_context import get_announcements

    try:
        data = get_announcements(course, since=since)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    output_format = (ctx.obj or {}).get("output_format")
    if output_format == "json":
        click.echo(json.dumps(data, indent=2, ensure_ascii=False))
        return

    if output_format == "md":
        for item in data:
            course_name = (item.get("Course") or {}).get("name", "")
            date = item.get("StartDate") or item.get("CreatedDate") or item.get("PublicationDate") or ""
            title = item.get("Title") or "(untitled)"
            body = item.get("Body") or {}
            text = body.get("Text", "") if isinstance(body, dict) else str(body)
            click.echo(f"## {title}\n\n- Course: {course_name}\n- Date: {date}\n\n{text.strip()}\n")
        if not data:
            click.echo("No course announcements found.")
        return

    click.echo("=== Course Announcements ===")
    if not data:
        click.echo("  (none)")
        return
    for item in data:
        course_name = (item.get("Course") or {}).get("name", "")
        date = item.get("StartDate") or item.get("CreatedDate") or item.get("PublicationDate") or ""
        title = item.get("Title") or "(untitled)"
        body = item.get("Body") or {}
        text = body.get("Text", "") if isinstance(body, dict) else str(body)
        preview = " ".join(text.split())
        if len(preview) > 180:
            preview = preview[:180] + "…"
        click.echo(f"\n[{date}] {course_name}\n{title}")
        if preview:
            click.echo(f"  {preview}")


@cli.command()
@click.option("--course", help="Limit calendar events to one course.")
@click.option("--days", type=click.IntRange(1, 366), default=14, show_default=True)
@click.pass_context
def calendar(ctx: click.Context, course: str | None, days: int) -> None:
    """Show upcoming Ufora calendar events."""
    args = ["calendar", "--days", str(days)]
    _append_option(args, "--course", course)
    _run(ctx, args)


@cli.command()
@click.option("--days", type=click.IntRange(1, 366), default=14, show_default=True)
@click.pass_context
def due(ctx: click.Context, days: int) -> None:
    """Show items due soon across courses."""
    _run(ctx, ["due", "--days", str(days)])


@cli.command()
@click.pass_context
def overdue(ctx: click.Context) -> None:
    """Show overdue Ufora items."""
    _run(ctx, ["overdue"])


@cli.command()
@click.argument("course", required=False)
@click.pass_context
def updates(ctx: click.Context, course: str | None) -> None:
    """Show unread/update counts globally or for COURSE."""
    args = ["updates"]
    if course:
        args.append(course)
    _run(ctx, args)


@cli.command()
@click.option("--course", help="Limit the snapshot to one course.")
@click.option("--shallow", is_flag=True, help="Skip expensive/deep content retrieval.")
@click.option("--since", type=click.IntRange(1, 24 * 365), help="Only include changes from the last N hours.")
@click.pass_context
def dump(ctx: click.Context, course: str | None, shallow: bool, since: int | None) -> None:
    """Emit a broad academic snapshot for an AI agent."""
    args = ["dump"]
    _append_option(args, "--course", course)
    if shallow:
        args.append("--shallow")
    _append_option(args, "--since", since)
    _run(ctx, args)


@cli.command()
@click.argument("course")
@click.argument("assignment")
@click.option("-o", "--output", type=click.Path(file_okay=False, path_type=str), help="Destination directory.")
@click.pass_context
def download(ctx: click.Context, course: str, assignment: str, output: str | None) -> None:
    """Download assignment attachments. For lecture/course files, use download-content."""
    args = ["download", course, assignment]
    _append_option(args, "-o", output)
    _run(ctx, args)


@cli.command(name="download-content")
@click.argument("course")
@click.argument("target")
@click.option("-o", "--output", type=click.Path(file_okay=False, path_type=str), help="Destination directory.")
@click.pass_context
def download_content(ctx: click.Context, course: str, target: str, output: str | None) -> None:
    """Download a course file/topic or all files in a module.

    TARGET may be a module title, topic title, full path such as
    `Slides / Tactics`, or a numeric topic ID returned by `ufora search`.
    """
    from .materials import MaterialNotFound, download_single_content_file

    destination = output or "."
    try:
        result = download_single_content_file(course, target, destination)
    except MaterialNotFound:
        result = None
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    if result is not None:
        click.echo(
            f"Downloaded {result['filename']} ({result['size_bytes']} bytes) -> {result['path']}"
        )
        return

    args = ["download-content", course, target]
    _append_option(args, "-o", output)
    _run(ctx, args)


@cli.command()
@click.option("--transport", type=click.Choice(["stdio", "http"]), default="stdio", show_default=True)
@click.option("--host", default="127.0.0.1", show_default=True, help="HTTP bind host; loopback only in v1.")
@click.option("--port", type=click.IntRange(1, 65535), default=8765, show_default=True)
@click.option("--path", "mcp_path", default="/mcp", show_default=True)
def mcp(transport: str, host: str, port: int, mcp_path: str) -> None:
    """Run the read-only Ufora MCP server via stdio or local HTTP."""
    from .mcp_server import run_server

    try:
        run_server(transport=transport, host=host, port=port, path=mcp_path)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc


@cli.group()
def skill() -> None:
    """Install or inspect the companion AI-agent skill."""


@skill.command("install")
@click.option(
    "--destination",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path.home() / ".agents" / "skills" / "ufora",
    show_default=True,
    help="Directory in which SKILL.md should be installed.",
)
def install_skill(destination: Path) -> None:
    """Install the bundled Ufora agent skill into a local skills directory."""
    source = resources.files("ufora_cli").joinpath("data", "SKILL.md")
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / "SKILL.md"
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    click.echo(f"Installed Ufora skill: {target}")


@skill.command("show")
def show_skill() -> None:
    """Print the bundled agent skill."""
    source = resources.files("ufora_cli").joinpath("data", "SKILL.md")
    click.echo(source.read_text(encoding="utf-8"))


if __name__ == "__main__":
    cli(prog_name="ufora")
