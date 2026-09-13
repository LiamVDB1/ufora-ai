# For Ghent University reviewers

Ufora AI is an **unofficial, student-built, open-source, read-only integration** for UGent Ufora.

The goal is simple: let students use the Ufora information they already have access to through a clean CLI and the open Model Context Protocol (MCP), so personal AI tools can understand courses, announcements, deadlines, grades, and course materials without screen scraping.

## What v1 does

v1 runs entirely on the student's own computer.

- The student logs into Ufora through the normal UGent browser/SSO flow.
- Authentication/session material stays on that computer.
- Requests go directly from the student's machine to Ufora's existing student-visible Brightspace APIs.
- The project has no analytics, telemetry, cloud account, credential proxy, or student-data backend.
- The student/course-data API surface is read-only; the separate browser authentication flow performs only the requests needed to establish the local session/token.
- Local HTTP MCP is restricted to loopback; it is not exposed as a network service.

The full source, tests, privacy policy, security boundary, and dated pre-outreach security review are intended to be publicly reviewable. See [`SECURITY-REVIEW.md`](SECURITY-REVIEW.md) for the threat model, fixed findings, verification evidence, and residual risks.

## Authentication mechanism to review

v1 does **not** register itself as an OAuth application in Ufora. The pinned `d2l-cli` dependency launches a dedicated local Chromium profile, lets the student complete the normal UGent SSO flow on UGent/Ufora pages, and then retrieves a Brightspace web bearer token from the authenticated browser session. The resulting browser profile/token state is stored only under the student's local `~/.d2l/` directory. Ufora AI never receives the student's password or MFA secret.

On the UGent student account used during development, the captured token's `scope` claim was `*:*:*`. Ufora AI's course/student-data read-only guarantee therefore comes from its GET-only Brightspace data client and the absence of write tools, **not** from a least-privilege OAuth grant. The login helper separately uses Brightspace authentication endpoints to establish that token. The token itself is treated as a sensitive credential.

This authentication approach is deliberately disclosed as the main v1 integration point for institutional review. [D2L recommends registered OAuth 2.0](https://community.d2l.com/brightspace/kb/articles/1134-brightspace-api-authentication-guide-oauth-2-0) for third-party Brightspace API applications; if UGent prefers that model even for a local client, migrating to an institution-registered least-privilege OAuth flow would be the correct next step rather than hiding the current browser-session mechanism.

The generic Brightspace/authentication layer currently comes from the pinned, MIT-licensed [`d2l-cli==0.2.2`](https://github.com/Aaryan-Kapoor/d2l-cli) dependency. Ufora AI adds its own UGent compatibility, safety, material-reading, CLI, and MCP layers on top. Because authentication is security-sensitive, that dependency should be included explicitly in an institutional code/security review rather than treated as a black box.

## UGent governance and privacy context

UGent's published [Ufora privacy statement](https://www.ugent.be/student/en/ict/educational-tools/ufora/privacystatement) identifies user data, course/content data, and action data as personal data handled inside the university's controlled Ufora environment. Ufora AI v1 itself has no backend, but a student can choose to pass requested Ufora results to an MCP/AI client; a cloud client may then process those results outside the local machine under that client's own terms.

This downstream client boundary needs an explicit institutional decision. UGent's current [student guidance for working safely with IT](https://helpdesk.ugent.be/security/veilig-werken-studenten.php) says not to store confidential information (including personal data) on cloud services with data storage outside the EEA. A general recommendation to connect Ufora AI to arbitrary personal cloud-AI accounts would therefore be premature. For ChatGPT specifically, OpenAI currently documents European data residency for eligible Enterprise/Edu workspaces and eligible API customers, not as a blanket guarantee for personal consumer accounts. If UGent wants a ChatGPT workflow, a managed/approved environment with the required residency and governance is the cleaner target.

There is also a separate **course-material permission/copyright boundary**. UGent's current [student GenAI guidance](https://www.ugent.be/student/en/study-support/genai) says course materials are not automatically permitted to be uploaded to an AI system: they may be copyrighted and may not belong to the student, so permission or lecturer-provided access through an approved AI system may be required. An MCP client receiving a Ufora PDF/slide/module body for cloud-model processing is materially the same data-disclosure question. The local software therefore should not be interpreted as granting permission to send all Ufora material to arbitrary AI providers.

UGent's [ICT acceptable-use policy](https://helpdesk.ugent.be/account/en/REG000157EN.pdf) permits legitimate education/research/service activities, while also prohibiting violations of system security/terms and deliberate disclosure of confidential information to unauthorized recipients. Ufora AI does not claim that those general rules constitute approval of this integration. Before broad institutional promotion, the intended API/authentication use, acceptable AI clients, data-residency expectations, course-material permission model, and recommended data-handling patterns should be confirmed with the Ufora/ICT/privacy/education owners.

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
- content topics can expose descriptions and file-backed material through student-visible Brightspace API surfaces.

These behaviors are covered by synthetic regression tests rather than private student-data fixtures.

See `docs/COMPATIBILITY.md`.

## Suggested review/pilot path

A low-risk way to evaluate the project would be:

1. technical/security review of the public repository, pinned authentication dependency, and `docs/SECURITY-REVIEW.md`;
2. verify that the project only consumes permitted student-visible read surfaces;
3. confirm whether the local browser-token mechanism is acceptable for a pilot;
4. define which AI/MCP clients and data-residency configurations may receive Ufora data, which data categories (for example grades) need stricter handling, and when course materials may be sent to an AI system;
5. small voluntary student pilot of the local v1 installation, preferably starting with the CLI/local data path before any broad cloud-AI recommendation;
6. collect compatibility/onboarding feedback;
7. decide whether UGent wants to link to, recommend, co-maintain, or simply acknowledge the project.

No UGent infrastructure change is technically required to run this local v1, but institutional review/approval is still recommended before UGent promotes it broadly to students.

## Optional future: official hosted connector

A one-click hosted ChatGPT/remote-MCP experience would have a different architecture. It should not reuse v1's local browser-session approach.

The clean version would use Brightspace's official OAuth authorization-code/refresh-token flow. For that, an administrator would register an OAuth application in Ufora/Manage Extensibility and provide the permitted redirect URI/scopes/client credentials to the hosted service operator.

That future version would require a separate privacy/security review because server-side token storage and multi-user authorization are real new risks. The repository deliberately keeps that out of v1.

## Questions worth discussing with UGent

- Is use of these student-visible Brightspace API surfaces acceptable for an open-source local integration?
- Is there a preferred contact/owner for Ufora extensibility/API questions?
- Would UGent be interested in reviewing or piloting the project with students?
- Which local or cloud AI/MCP clients and data-residency configurations would UGent consider acceptable for Ufora data?
- Under what conditions may student-accessible course materials be passed from Ufora to an AI system, and can UGent/lecturers provide an approved permission model for that workflow?
- If ChatGPT is a desired client, would UGent prefer a managed ChatGPT Edu/approved environment rather than personal accounts?
- If a hosted version became desirable, what read-only OAuth scopes and registration process would UGent prefer?
- Are there branding/disclaimer requirements UGent would like an unofficial integration to follow?

## Contact / project ownership

The project is maintained as an independent open-source student project by Liam Van den Broeck. It should not be represented as an official UGent service unless UGent explicitly chooses to adopt or endorse it.
