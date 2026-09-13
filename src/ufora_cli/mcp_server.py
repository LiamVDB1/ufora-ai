from __future__ import annotations

import argparse
import ipaddress
from importlib import resources
from typing import Any

from mcp.server import MCPServer

from . import __version__
from .core import UFORA_HOST, run_d2l_json

PROJECT_URL = "https://github.com/LiamVDB1/ufora-ai"
DEFAULT_HTTP_HOST = "127.0.0.1"
DEFAULT_HTTP_PORT = 8765
DEFAULT_HTTP_PATH = "/mcp"

mcp = MCPServer(
    "ufora-ai",
    title="Ufora AI",
    description="Unofficial read-only MCP access to UGent Ufora (D2L Brightspace).",
    instructions=(
        "Use these tools for the authenticated student's UGent Ufora data. "
        "The integration is read-only. Prefer current academic-year courses unless "
        "the user explicitly asks for historical courses. UGent group enrollments "
        "such as GR01 are not separate courses. For course material, inspect the "
        "detailed content tree first and then use read_course_material for the actual "
        "PDF/text when needed. If authentication is stale, ask the user to run "
        "`ufora login` locally; never request passwords, bearer tokens, or cookies."
    ),
    website_url=PROJECT_URL,
    version=__version__,
)


def _call(*args: str) -> Any:
    return run_d2l_json(args)


def _skill_text() -> str:
    try:
        return resources.files("ufora_cli").joinpath("data", "SKILL.md").read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError):
        return "See the project documentation at " + PROJECT_URL


def _is_loopback_host(host: str) -> bool:
    normalized = host.strip().lower()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


@mcp.resource("ufora://about")
def about() -> dict[str, str]:
    """Basic information about this Ufora integration."""
    return {
        "name": "Ufora AI",
        "version": __version__,
        "institution": "Ghent University (UGent)",
        "service": "Ufora",
        "platform": "D2L Brightspace",
        "host": UFORA_HOST,
        "access": "read-only",
        "project_url": PROJECT_URL,
        "login_command": "ufora login",
    }


@mcp.resource("ufora://guide")
def guide() -> str:
    """Agent-facing usage guide, including UGent-specific Brightspace quirks."""
    return _skill_text()


@mcp.tool()
def doctor() -> Any:
    """Check Ufora host, authentication, API readiness, and current-course discovery."""
    return _call("doctor")


@mcp.tool()
def whoami() -> Any:
    """Return the currently authenticated UGent Ufora user."""
    return _call("whoami")


@mcp.tool()
def list_courses(include_all: bool = False, query: str | None = None) -> Any:
    """List courses, or search real course offerings by name/code/ID.

    Without QUERY this returns the current academic year unless include_all is
    true. With QUERY it searches all real course offerings, including history.
    """
    if query:
        data = _call("courses", "--all")
        enrollments = data if isinstance(data, list) else []
        needle = query.casefold().strip()
        return [
            enrollment
            for enrollment in enrollments
            if any(
                needle in str(enrollment.get("OrgUnit", {}).get(field) or "").casefold()
                for field in ("Name", "Code", "Id")
            )
        ]

    args = ["courses"]
    if include_all:
        args.append("--all")
    return _call(*args)


@mcp.tool()
def get_upcoming_due(days: int = 14) -> Any:
    """Return items due across current Ufora courses in the next N days."""
    if not 1 <= days <= 366:
        raise ValueError("days must be between 1 and 366")
    return _call("due", "--days", str(days))


@mcp.tool()
def get_overdue() -> Any:
    """Return overdue Ufora items across current courses."""
    return _call("overdue")


@mcp.tool()
def get_calendar(days: int = 14, course: str | None = None) -> Any:
    """Return upcoming calendar events, optionally restricted to one course."""
    if not 1 <= days <= 366:
        raise ValueError("days must be between 1 and 366")
    args = ["calendar", "--days", str(days)]
    if course:
        args.extend(["--course", course])
    return _call(*args)


@mcp.tool()
def get_announcements(course: str | None = None, since: str | None = None) -> Any:
    """Return actual course announcements with full body text/HTML.

    Without ``course``, aggregates News across current academic-year courses;
    this does not use Brightspace's separate Activity Feed.
    """
    from .course_context import get_announcements as read_announcements

    return read_announcements(course, since=since)


@mcp.tool()
def get_course_overview(course: str) -> Any:
    """Return the dedicated Ufora Course Overview with course expectations and description text."""
    if not course.strip():
        raise ValueError("course must not be empty")
    from .materials import get_course_overview as read_overview

    return read_overview(course)


@mcp.tool()
def get_grades(course: str) -> Any:
    """Return grade items and feedback for one course."""
    if not course.strip():
        raise ValueError("course must not be empty")
    return _call("grades", course)


@mcp.tool()
def get_final_grades() -> Any:
    """Return final grades across currently resolved courses."""
    return _call("grades", "--final")


@mcp.tool()
def get_assignments(course: str) -> Any:
    """Return Brightspace assignment folders and due dates for one course."""
    if not course.strip():
        raise ValueError("course must not be empty")
    return _call("assignments", course)


@mcp.tool()
def get_quizzes(course: str) -> Any:
    """Return quizzes and timing metadata for one course."""
    if not course.strip():
        raise ValueError("course must not be empty")
    return _call("quizzes", course)


@mcp.tool()
def get_course_context(
    course: str,
    days: int = 14,
    include_content: bool = True,
    announcement_limit: int = 20,
) -> Any:
    """Return high-value context for one course: Overview, announcements, assessments, deadlines, and content."""
    if not course.strip():
        raise ValueError("course must not be empty")
    from .course_context import get_course_context as build_context

    return build_context(
        course,
        days=days,
        include_content=include_content,
        announcement_limit=announcement_limit,
    )


@mcp.tool()
def get_course_content(course: str, detailed: bool = True) -> Any:
    """Return course modules/topics; detailed mode includes descriptions, URLs, types, and nesting."""
    if not course.strip():
        raise ValueError("course must not be empty")
    args = ["content", course]
    if detailed:
        args.append("--toc")
    return _call(*args)


@mcp.tool()
def search_course_content(course: str, query: str, limit: int = 20) -> Any:
    """Search Course Overview, module bodies, topics, and descriptions for one course."""
    if not course.strip():
        raise ValueError("course must not be empty")
    if not query.strip():
        raise ValueError("query must not be empty")
    from .materials import search_course_content as search_content

    return search_content(course, query, limit=limit)


@mcp.tool()
def read_course_material(course: str, material: str, max_chars: int = 60000) -> Any:
    """Read a Course Overview, module body, topic, or extractable PDF/text material."""
    if not course.strip():
        raise ValueError("course must not be empty")
    if not material.strip():
        raise ValueError("material must not be empty")
    from .materials import read_material

    return read_material(course, material, max_chars=max_chars)


@mcp.tool()
def get_discussions(course: str) -> Any:
    """Return discussion forums/topics/posts exposed by Brightspace for one course."""
    if not course.strip():
        raise ValueError("course must not be empty")
    return _call("discussions", course)


@mcp.tool()
def get_updates(course: str | None = None) -> Any:
    """Return unread/update counters globally or for one course."""
    args = ["updates"]
    if course:
        args.append(course)
    return _call(*args)


@mcp.tool()
def get_snapshot(
    course: str | None = None,
    shallow: bool = False,
    since_hours: int | None = None,
) -> Any:
    """Return a broad AI-oriented academic snapshot."""
    if since_hours is not None and not 1 <= since_hours <= 24 * 365:
        raise ValueError("since_hours must be between 1 and 8760")
    args = ["dump"]
    if course:
        args.extend(["--course", course])
    if shallow:
        args.append("--shallow")
    if since_hours is not None:
        args.extend(["--since", str(since_hours)])
    return _call(*args)


def run_server(
    *,
    transport: str = "stdio",
    host: str = DEFAULT_HTTP_HOST,
    port: int = DEFAULT_HTTP_PORT,
    path: str = DEFAULT_HTTP_PATH,
) -> None:
    """Run Ufora MCP over stdio or local-only Streamable HTTP."""
    if transport == "stdio":
        mcp.run("stdio")
        return

    if transport not in {"http", "streamable-http"}:
        raise ValueError("transport must be 'stdio' or 'http'")
    if not _is_loopback_host(host):
        raise ValueError(
            "Ufora AI v1 only serves HTTP on a loopback address. "
            "A network/public deployment would expose a student's local Ufora session; "
            "use 127.0.0.1/localhost, or build the separate OAuth-backed hosted service."
        )
    if not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    if not path.startswith("/"):
        raise ValueError("MCP path must start with '/'")

    mcp.run(
        "streamable-http",
        host=host,
        port=port,
        streamable_http_path=path,
        json_response=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Ufora AI MCP server")
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--host", default=DEFAULT_HTTP_HOST, help="HTTP bind host (loopback only in v1)")
    parser.add_argument("--port", type=int, default=DEFAULT_HTTP_PORT)
    parser.add_argument("--path", default=DEFAULT_HTTP_PATH, help="Streamable HTTP MCP path")
    args = parser.parse_args()
    run_server(transport=args.transport, host=args.host, port=args.port, path=args.path)


if __name__ == "__main__":
    main()
