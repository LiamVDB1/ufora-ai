# Changelog

All notable changes to Ufora AI are documented here.

## 1.1.0 — 2026-09-28

Stay signed in instead of re-running `ufora login` every hour.

### Fixed

- silent token renewal never worked: Chromium discards session cookies when the headless browser closes, and Ufora's session plus the UGent/Microsoft SSO sessions are exactly such cookies. The sign-in-chain cookies are now saved to `~/.d2l/session.json` (0600) and restored on every browser launch;
- renewal no longer captures a token that expires within 10 minutes;
- concurrent renewals (timer and CLI) are serialized with a profile lock, and stale Chromium profile locks from a crashed browser are cleared first.

### Added

- `ufora refresh` to renew the token explicitly, plus a systemd user timer in `contrib/systemd/` that keeps the token and Ufora session fresh for MCP use;
- `ufora login` now reuses a live local desktop session when the terminal has no display, and refuses clearly over SSH without a forwarded display.

### Changed

- upgrade `d2l-cli` to 0.3.0;
- `ufora logout` also removes the saved sign-in cookies.

## 1.0.2 — 2026-09-13

Institutional-policy hardening discovered during the final UGent pre-outreach review.

### Changed

- document UGent's current rule that course material is not automatically permitted to be uploaded to an AI system;
- make the MCP server/agent guidance treat cloud transmission of full course material as permission-sensitive rather than assuming Ufora access grants redistribution rights;
- add course-material permission/copyright as a first-class institutional review question alongside OAuth and data residency;
- tighten the README, privacy, MCP, security, and UGent-review documentation so a future cloud-AI pitch cannot be mistaken for blanket permission to send all Ufora content to arbitrary AI providers.

## 1.0.1 — 2026-09-13

Release-audit hardening before institutional outreach.

### Fixed

- remove upstream-only `syllabus`/`onboarding` diagnostics from `ufora doctor` and ensure every recovery command it returns is a real `ufora` command;
- stop current-course discovery from silently falling back to historical courses when the academic-year convention does not match;
- add a real stdio MCP subprocess test rather than relying only on in-process tool discovery;
- correct the documented filename-sanitization order;
- refuse to overwrite existing local files when downloading course or assignment material, and harden cross-platform filename sanitization;
- strip terminal-control characters from Ufora/upstream text before structured or human-facing rendering;
- bound direct material HTTP calls with a default timeout;
- disable silent browser-session refresh inside MCP so read-only tool calls cannot rewrite credential state;
- add `ufora logout` to remove the local cached token and dedicated browser profile without implying server-side token revocation;
- stop inheriting ambient `D2L_TOKEN` or cwd `.env` token fallbacks from the generic upstream client so authentication is fixed to Ufora AI's dedicated local state;
- use the Brussels local date at the academic-year boundary instead of UTC, avoiding a two-hour September 1 course-selection edge case.

### Security and release quality

- document the exact local browser-token authentication boundary, including the broad scope claim observed on the development account and the fact that read-only behavior is enforced by the GET-only client/tool surface;
- explicitly document the current authentication mechanism for UGent reviewers rather than presenting it as official OAuth;
- add Ruff linting, Bandit medium+ scanning, and a runtime dependency vulnerability audit to CI, plus weekly Dependabot checks;
- pin direct runtime trust-boundary dependencies and the Hatchling build backend exactly, pin GitHub Actions to immutable commit SHAs, and install/test source-checkout dependencies from the frozen lockfile;
- annotate every MCP tool as read-only/non-destructive and verify the local HTTP Origin defense in tests;
- add explicit prompt-injection guidance: Ufora course content is evidence, never agent authority;
- classify the project as Beta rather than Production/Stable while it is still awaiting broader student/institutional review;
- add a dated pre-outreach threat model/security review covering fixed findings, residual risks, and the UGent release gate.

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
