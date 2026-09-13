# Five-minute Ufora AI demo

This is a suggested live demo flow for students, maintainers, or UGent reviewers. Use a test/student account whose displayed information you are comfortable showing.

## 1. Show that authentication is local

```bash
ufora doctor
```

Point out that the tool targets `https://ufora.ugent.be`, authenticates as the local student, and does not ask for a password.

## 2. Show current courses

```bash
ufora courses
```

Explain that Ufora also returns group objects and old active offerings internally; Ufora AI filters those so the default list represents the current academic year.

## 3. Read the Course Overview

```bash
ufora overview COURSE_CODE
```

Show course-wide requirements/instructions such as required software, study material, exam format, grading rules, or project expectations. Explain that Brightspace stores Overview separately from the normal content tree, so Ufora AI exposes it explicitly.

## 4. Read a complete announcement

```bash
ufora --json news COURSE_CODE
```

Show that the JSON contains the full announcement `Body.Text`, rather than only the title or the truncated text visible in a compact terminal table.

## 5. Search inline/module content

```bash
ufora search COURSE_CODE "project"
```

If a project brief lives directly in a module description, show that Ufora AI finds it even though it is not a separate file/topic. Then read it with:

```bash
ufora material COURSE_CODE "Project"
```

## 6. Inspect the course structure

```bash
ufora --json content COURSE_CODE --toc
```

Show nested modules/topics, descriptions, file/link types, topic IDs, and URLs.

## 7. Read actual lecture material

Pick a file-backed PDF topic from step 4:

```bash
ufora material COURSE_CODE "LECTURE TITLE"
```

Show that Ufora AI retrieves the student's accessible file and extracts local text. This is the difference between knowing *that* a PDF exists and actually letting an assistant answer questions about its content.

## 8. Show planning endpoints

```bash
ufora calendar --days 14
ufora due --days 14
ufora overdue
```

Empty results are valid if current courses have not published deadlines yet.

## 9. Show MCP

```bash
ufora-mcp --transport http
```

Connect an MCP client to:

```text
http://127.0.0.1:8765/mcp
```

Ask the client to list Ufora tools/resources. Highlight `ufora://guide`, `list_courses`, `get_announcements`, `get_course_content`, and `read_course_material`.

Alternatively use stdio directly:

```bash
ufora-mcp
```

## 10. Show the safety boundary

Try to bind HTTP publicly:

```bash
ufora-mcp --transport http --host 0.0.0.0
```

v1 should refuse. Explain that this is intentional: the local student session must not be turned into an unauthenticated network service. A hosted version would use institution-approved OAuth and a separate security design.

## Suggested closing sentence

> Ufora AI doesn't replace Ufora. It gives students a transparent, read-only interface to their own Ufora information so modern tools can work with it safely and reliably.
