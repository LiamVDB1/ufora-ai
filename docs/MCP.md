# MCP integration

Ufora AI exposes the same read-only Ufora capabilities through MCP that are available through the CLI.

## Transports

### stdio

Preferred for local clients:

```bash
ufora-mcp
```

Equivalent:

```bash
ufora mcp
```

Example configuration:

```json
{
  "mcpServers": {
    "ufora": {
      "command": "ufora-mcp"
    }
  }
}
```

Codex CLI:

```bash
codex mcp add ufora -- ufora-mcp
```

### Streamable HTTP

For local clients that require HTTP:

```bash
ufora-mcp --transport http
```

Default endpoint:

```text
http://127.0.0.1:8765/mcp
```

Custom loopback endpoint:

```bash
ufora-mcp --transport http --host 127.0.0.1 --port 9000 --path /mcp
```

Ufora AI v1 rejects non-loopback hosts. This is intentional: the local server uses the student's local authenticated Ufora session and must not become an unauthenticated network service.

## Resources

### `ufora://about`

Returns project/version/institution metadata and the local login command.

### `ufora://guide`

Returns the bundled agent usage guide. Clients can use it to learn UGent-specific course semantics, tool-selection patterns, and safety rules.

## Tools

| Tool | Purpose |
| --- | --- |
| `doctor` | Check host, authentication, API readiness, and current-course discovery. |
| `whoami` | Return the authenticated Ufora user. |
| `list_courses` | Current academic-year courses; `include_all=true` adds history, and `query=...` searches all real course offerings by name/code/ID. |
| `get_upcoming_due` | Due items across current courses. |
| `get_overdue` | Overdue items across current courses. |
| `get_calendar` | Calendar events globally/current courses or one course. |
| `get_announcements` | Full course News including body text/HTML; without a course, aggregates announcements across current courses rather than using Brightspace's separate Activity Feed. |
| `get_course_overview` | Dedicated Brightspace Course Overview: requirements, software, grading, exam/project rules, etc. |
| `get_course_context` | High-value one-course bundle: Overview, announcements, assessments, deadlines, updates, and optional content tree. |
| `get_grades` | Grade items for one course. |
| `get_final_grades` | Final grades across currently resolved courses. |
| `get_assignments` | Brightspace assignment folders/due dates. |
| `get_quizzes` | Quiz metadata and timing. |
| `search_course_content` | Search Course Overview, module bodies, topics, paths, and descriptions. |
| `get_course_content` | Nested modules/topics; detailed mode includes descriptions/URLs/types. This does not include the separate Course Overview. |
| `read_course_material` | Read Overview/module/inline content or extract PDF/text topic content when possible. |
| `get_discussions` | Discussion data exposed by Brightspace. |
| `get_updates` | Unread/update counters. |
| `get_snapshot` | Broad AI-oriented academic snapshot. |

## Recommended agent pattern

For questions about course requirements/structure:

```text
list_courses(query=...) when the course is historical/unclear
    -> get_course_overview(course)
    -> get_course_context(course) when a broader briefing is useful
```

For questions about specific course material:

```text
search_course_content(course, query)
    -> identify relevant Overview/module/topic
    -> read_course_material(course, item title, full path such as `Slides / Tactics`, or numeric ID)
    -> answer from the returned material
```

Use `get_course_content(course, detailed=true)` when the full nested hierarchy is itself useful. Course Overview is a separate Brightspace surface and must not be inferred from the TOC.

For planning questions:

```text
get_upcoming_due
+ get_overdue
+ get_calendar
+ relevant announcements
```

For “what changed?” questions, prefer `get_snapshot(since_hours=...)` or announcement cutoffs rather than fetching every historical course.

## Data semantics

The server is intentionally explicit about what a Brightspace endpoint does and does not prove. For example, `get_assignments(course)` returning an empty list only means that course has no visible items in Brightspace's Assignments/Dropbox surface. It does not prove the professor has assigned no work; course content/announcements may point to GitHub, Dodona, or another service.

## Authentication failures

MCP never accepts passwords/tokens as tool arguments. If a call reports that the session is stale, the correct recovery is:

```bash
ufora login
```

Then retry the MCP call.

## Hosted/public clients

v1 is not a hosted multi-user connector. Do not tunnel or expose its local HTTP endpoint to the public internet. A remote ChatGPT-style connector should use a separate OAuth-backed service with institutional approval and its own authentication/authorization layer.
