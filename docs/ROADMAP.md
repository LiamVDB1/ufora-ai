# Roadmap

## v1 — local open-source integration

Status: released; current audit-hardened release line starts at `1.0.1`.

- read-only CLI;
- stdio MCP;
- loopback Streamable HTTP MCP;
- browser-based local UGent/Ufora login;
- current/historical course discovery;
- announcements, deadlines, grades, assignments, quizzes, discussions, content, updates, snapshots;
- direct PDF/text material reading;
- bundled agent skill;
- privacy/security docs and tests;
- no backend, telemetry, or hosted student-data store.

## v1.x — polish and compatibility

Potential improvements that preserve the local trust model:

- easier signed/native installers for students who do not use Python tooling;
- broader Windows/Linux login verification;
- richer document extraction (for example DOCX/PPTX) without executing active content;
- cache controls for large course trees/materials;
- better diagnostics for unusual Ufora configurations;
- accessibility/onboarding improvements;
- optional institution-adapter interface once a second real deployment proves the abstraction.

## v2 — optional hosted connector

Only pursue this if there is real student/institution demand and UGent is comfortable with the architecture.

A hosted version requires:

- official Brightspace OAuth application registration;
- explicit user authorization and revocation;
- authenticated MCP access per student;
- encrypted refresh-token storage;
- least-privilege read scopes;
- secure secret/key management;
- audit logging that avoids course-content leakage;
- rate limiting and abuse prevention;
- deletion/retention policy;
- separate privacy/security review;
- operational ownership and incident response.

This should be a separate service/repository. It is not a flag that should be added to the local v1 process.

## Non-goals

Unless the project is deliberately re-scoped, the following are not planned:

- automating submissions;
- modifying grades;
- posting as students or staff;
- bypassing Ufora access controls;
- scraping data a student cannot already access;
- asking students to enter UGent passwords into a third-party hosted service.
