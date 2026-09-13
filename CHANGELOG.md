# Changelog

All notable changes to Ufora AI are documented here.

## 1.0.0 — 2026-09-13

First public-ready release.

### Added

- read-only `ufora` CLI for UGent Ufora;
- MCP server with stdio and loopback-only Streamable HTTP transports;
- MCP resources `ufora://about` and `ufora://guide`;
- current/historical course discovery;
- announcements, grades, assignments, quizzes, discussions, calendar, due/overdue, updates, and academic snapshots;
- dedicated Brightspace Course Overview access for course-wide requirements/instructions;
- one-course context bundles combining Overview, announcements, assessments, deadlines, updates, and content;
- search across Course Overview, module bodies, topics, paths, and descriptions;
- forgiving course discovery via `ufora courses QUERY` and MCP `list_courses(query=...)`;
- nested course-content discovery including module description bodies;
- direct reading of Overview/module/inline content and text extraction for PDF/text course materials;
- local course/module file downloads, including direct file-topic download by numeric topic ID;
- bundled AI-agent skill plus `ufora skill install`;
- public security, privacy, architecture, MCP, contribution, compatibility, demo, and UGent-review documentation;
- CI and regression tests for UGent compatibility and MCP security boundaries.

### UGent compatibility

- recognize localized `Cursuseditie` entries using Brightspace's stable `Course Offering` type code;
- exclude `GR01` and other group enrollments from course lists and course resolution;
- default cross-course operations to the current academic year so historical offerings do not break calendar/due endpoints;
- fix shallow snapshots so they retain course identities;
- URL-decode downloaded Ufora filenames;
- keep underlying `d2l-cli` commands/errors behind the public `ufora` abstraction;
- aggregate actual course News for `ufora news`/`get_announcements()` instead of exposing Brightspace's separate, potentially empty Activity Feed;
- resolve hierarchical material paths such as `Slides / Tactics` and expose module children when a module has no inline body;
- identify file-backed content as files rather than generic links;
- include `fonttools` so PDF extraction does not emit avoidable parser warnings for common embedded fonts.

### Security

- Ufora-facing surface remains read-only;
- local authentication state is permission-hardened where supported;
- child commands use argument arrays rather than shell interpolation;
- HTTP MCP refuses non-loopback interfaces in v1.
