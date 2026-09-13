# For Ghent University reviewers

Ufora AI is an **unofficial, student-built, open-source, read-only integration** for UGent Ufora.

The goal is simple: let students use the Ufora information they already have access to through a clean CLI and the open Model Context Protocol (MCP), so personal AI tools can understand courses, announcements, deadlines, grades, and course materials without screen scraping.

## What v1 does

v1 runs entirely on the student's own computer.

- The student logs into Ufora through the normal UGent browser/SSO flow.
- Authentication/session material stays on that computer.
- Requests go directly from the student's machine to Ufora's existing student-visible Brightspace APIs.
- The project has no analytics, telemetry, cloud account, credential proxy, or student-data backend.
- The Ufora-facing surface is read-only.
- Local HTTP MCP is restricted to loopback; it is not exposed as a network service.

The full source, tests, privacy policy, and security boundary are intended to be publicly reviewable.

## Why MCP

MCP is an open protocol for connecting AI clients to external tools/data. Ufora AI exposes explicit tools such as:

- list current courses;
- read an announcement including its complete body;
- inspect calendar/due items;
- read grade data;
- read the dedicated Course Overview (for example course requirements, software, exam/project rules, and grading information);
- inspect a nested content tree including substantial module-description pages;
- search across Overview, module bodies, topics, paths, and descriptions;
- retrieve and locally extract text from a student-accessible lecture PDF.

This is materially safer and more reliable than asking an AI agent to drive the Ufora web interface with browser automation.

## What v1 explicitly does not do

- submit assignments;
- create or edit discussions;
- modify grades;
- mark content read;
- impersonate staff;
- accept a student's UGent password as application input;
- operate a hosted database of student Ufora data;
- expose a student's local session over the public internet.

## UGent compatibility findings

During development against a real student account, several UGent-specific Brightspace behaviors were identified and documented:

- the localized course type name is `Cursuseditie` while the stable code remains `Course Offering`;
- group enrollments such as `GR01` appear alongside course enrollments and must not be treated as separate courses;
- historical offerings can remain active and can break naïve cross-course calendar/deadline queries;
- the Course Overview is a separate Brightspace API surface from the normal table of contents and can contain crucial course-wide information;
- module descriptions can contain complete project briefs/FAQs without being separate files or topics;
- content topics can expose descriptions and file-backed material through the official student API.

These behaviors are covered by synthetic regression tests rather than private student-data fixtures.

See `docs/COMPATIBILITY.md`.

## Suggested review/pilot path

A low-risk way to evaluate the project would be:

1. technical/security review of the public repository;
2. verify that the project only consumes permitted student-visible read surfaces;
3. small voluntary student pilot of the local v1 installation;
4. collect compatibility/onboarding feedback;
5. decide whether UGent wants to link to, recommend, co-maintain, or simply acknowledge the project.

No UGent infrastructure change is required for this local v1.

## Optional future: official hosted connector

A one-click hosted ChatGPT/remote-MCP experience would have a different architecture. It should not reuse v1's local browser-session approach.

The clean version would use Brightspace's official OAuth authorization-code/refresh-token flow. For that, an administrator would register an OAuth application in Ufora/Manage Extensibility and provide the permitted redirect URI/scopes/client credentials to the hosted service operator.

That future version would require a separate privacy/security review because server-side token storage and multi-user authorization are real new risks. The repository deliberately keeps that out of v1.

## Questions worth discussing with UGent

- Is use of these student-visible Brightspace API surfaces acceptable for an open-source local integration?
- Is there a preferred contact/owner for Ufora extensibility/API questions?
- Would UGent be interested in reviewing or piloting the project with students?
- If a hosted version became desirable, what read-only OAuth scopes and registration process would UGent prefer?
- Are there branding/disclaimer requirements UGent would like an unofficial integration to follow?

## Contact / project ownership

The project is maintained as an independent open-source student project by Liam Van den Broeck. It should not be represented as an official UGent service unless UGent explicitly chooses to adopt or endorse it.
