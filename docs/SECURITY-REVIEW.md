# Security review — 2026-09-13

This document records the pre-UGent security review of **Ufora AI 1.0.2**. It is intended to make the project's trust boundary, verified controls, fixed defects, and remaining institutional questions explicit rather than imply that an unofficial student integration is risk-free.

## Review conclusion

**Suitable to present to UGent for technical/security review and a limited voluntary pilot after 1.0.2 is released.**

It should **not** be presented as institutionally approved, production-grade for university-wide deployment, or as using an official least-privilege OAuth integration. Three institutional questions remain open. First, authentication: v1 locally captures a Brightspace web bearer token after normal UGent SSO. On the development account the token carried the broad scope claim `*:*:*`. Ufora AI's student/course-data client remains read-only because its reviewed API methods expose GET/read calls only; the separate login helper uses authentication requests to establish the token. Token compromise could still have impact beyond the application's intended read-only data surface. Second, AI-client data handling: Ufora contains personal/confidential student data, while UGent's current student IT guidance says not to store confidential information (including personal data) on cloud services whose data storage is outside the EEA. Third, course-material rights: UGent's current GenAI guidance says course materials are not automatically permitted to be uploaded to AI systems because they may be copyrighted and may not belong to the student. A broad rollout to arbitrary cloud AI accounts therefore needs explicit UGent-approved data-handling/residency **and course-material permission** policies.

The recommended UGent discussion is therefore not “is this perfectly secure?” but:

1. are the student-visible Brightspace read APIs used by this project acceptable for a local open-source client;
2. is the current local browser-session token mechanism acceptable for a pilot;
3. if not, can UGent register a least-privilege OAuth client for the project;
4. which MCP/AI client deployments UGent considers acceptable for student data, including EEA data-residency requirements;
5. under what conditions student-accessible course material may be sent to an AI system;
6. whether a UGent-managed ChatGPT Edu/other approved AI environment should be the target for any institutionally promoted cloud-AI workflow instead of arbitrary personal accounts.

## Scope

Reviewed surfaces:

- local browser/token authentication and credential storage;
- Brightspace API client and course resolution;
- CLI command construction and subprocess boundaries;
- MCP stdio and local Streamable HTTP transports;
- course content, announcements, links, filenames, PDFs, and prompt-injection exposure;
- local file downloads and extraction;
- error/output handling and terminal-control injection;
- dependency and GitHub Actions supply chain;
- secret leakage, release packaging, and repository history;
- privacy/security documentation and institutional claims;
- UGent cloud-data guidance and the downstream AI-client data-residency boundary.

Out of scope:

- vulnerabilities inside UGent Ufora/Brightspace itself;
- a fully compromised student operating-system account;
- a malicious MCP/AI client the student deliberately authorizes to receive their data;
- a future hosted/multi-user OAuth service, which is a separate trust boundary and requires its own review.

## Threat model

### Assets

- Brightspace bearer token and saved browser session;
- private student data: enrollments, announcements, grades, deadlines, discussions, and course materials;
- local filesystem integrity;
- the authority of an MCP-connected AI client and any other tools available to that client;
- release integrity of the public repository and packages.

### Relevant attackers / failure sources

- hostile or compromised course content that reaches an AI as untrusted text;
- malicious filenames/files published in a course;
- another local process while loopback HTTP MCP is running;
- a compromised dependency or mutable CI action;
- accidental secret publication by a maintainer;
- malformed/expensive PDFs or stalled network responses causing resource exhaustion.

### Trust boundaries

```text
UGent SSO/browser
      │
      ▼
local Brightspace token/profile  ← sensitive credential boundary
      │
      ▼
Ufora AI GET-only client
      │
      ├────────► terminal output
      │
      ├────────► local downloaded files
      │
      └────────► MCP client / AI  ← untrusted course data crosses into an agent context
```

## Findings

| ID | Finding | Severity / priority | Status |
| --- | --- | --- | --- |
| SR-01 | Browser-derived Brightspace token is not a project-specific least-privilege OAuth grant; observed scope was `*:*:*` | **High credential impact / institutional blocker** | **Open — requires UGent/auth decision** |
| SR-02 | Course-controlled download filenames could overwrite an existing local file in the selected directory | **Medium** | **Fixed in 1.0.1** |
| SR-03 | Course pages/PDFs/announcements can contain prompt-injection-like instructions consumed by an AI client | **Medium** | **Mitigated; residual agent risk remains** |
| SR-04 | Loopback HTTP MCP has no application-level user authentication | **Low–Medium** | **Accepted for trusted single-user local use; stdio preferred** |
| SR-05 | Course/upstream text could contain terminal control sequences | **Low** | **Fixed in 1.0.1** |
| SR-06 | Direct material HTTP calls had no default timeout | **Low availability risk** | **Fixed in 1.0.1** |
| SR-07 | A nominally read-only MCP call could trigger silent browser-session refresh and rewrite local credential state | **Low–Medium semantic/trust issue** | **Fixed in 1.0.1** |
| SR-08 | Authentication relies on security-sensitive third-party `d2l-cli` code | **Medium supply-chain / review priority** | **Mitigated, residual dependency remains** |
| SR-09 | PDF extraction can still consume significant CPU/RAM on adversarial material | **Low–Medium availability risk** | **Partially mitigated; residual** |
| SR-10 | Secret/release-package leakage | **High if present** | **No leak found in reviewed history/artifacts** |
| SR-11 | Generic upstream auth could inherit a valid `D2L_TOKEN` from the process environment or cwd `.env`, making the effective account depend on ambient state | **Low–Medium auth-integrity risk** | **Fixed in 1.0.1** |
| SR-12 | Cloud AI/MCP clients may store Ufora personal/confidential data outside the EEA or otherwise outside an UGent-approved data-handling boundary | **High institutional/privacy priority** | **Open — deployment policy/client choice required** |
| SR-13 | Course materials may be copyrighted/not owned by the student; sending them to an AI client is not automatically permitted by UGent policy | **High institutional/legal priority** | **Open — permission/approved-AI model required** |

### SR-01 — authentication trust boundary

The local login flow opens a dedicated browser profile, lets the student complete normal UGent SSO, then captures a Brightspace web bearer token from that authenticated browser context. The password/MFA secret is not accepted by Ufora AI itself.

The observed token scope means **the token's permissions are broader than Ufora AI's interface**. The project's student/course-data read-only property is instead enforced by the application: reviewed data API methods use GET/read operations and the MCP surface exposes no Ufora writes. The login helper separately performs authentication requests required to obtain the token.

Controls already present:

- token/browser state remains local under `~/.d2l/`;
- local POSIX permissions are hardened (`~/.d2l` to `0700`, token file to `0600` where supported);
- `ufora logout` removes the local token and dedicated browser profile without following a symlinked profile path; it does not claim server-side revocation of an already-issued token;
- token/password/cookies are never MCP arguments;
- no telemetry or hosted credential proxy;
- documentation explicitly discloses this mechanism to UGent.

Residual risk: theft of the underlying token is more serious than theft of a hypothetical least-privilege read-only project token. For institutional endorsement, the preferred target is an institution-registered OAuth flow with the narrowest scopes UGent permits.

### SR-02 — local file clobbering

Previously, path traversal was stripped from Ufora-provided filenames, but a valid basename could still replace an existing local file when the user downloaded course or assignment material.

1.0.1 now:

- URL-decodes then removes path components;
- rejects hidden/control-character and Windows-reserved filenames;
- normalizes characters illegal on common filesystems;
- bounds filename byte length;
- creates downloads using exclusive `xb` semantics;
- refuses to overwrite an existing file or symlink;
- keeps assignment/module download writes inside Ufora AI instead of falling back to the upstream writer.

Regression tests cover direct topic files, recursive modules, assignment attachments, encoded traversal-style names, hidden/control names, Windows-reserved names, and overwrite refusal.

### SR-03 — indirect prompt injection

Ufora data is trusted as *course evidence*, not as *agent instructions*. A professor account, compromised account, external link, announcement, module body, PDF, or filename can contain text such as “ignore previous instructions” or “send your secrets here”.

Controls:

- MCP server instructions explicitly mark all Ufora-returned data as untrusted;
- the bundled skill repeats that boundary;
- downloaded code/binaries/macros are never executed by Ufora AI;
- there are no Ufora write tools for injected content to trigger;
- the skill forbids executing/installing/calling unrelated tools merely because retrieved material says to do so.

Residual risk cannot be eliminated inside this MCP server: an AI client may have unrelated powerful tools. The client must preserve the distinction between user/system authority and retrieved course data.

### SR-04 — loopback HTTP MCP

HTTP MCP is restricted to loopback addresses and the MCP stack validates Host/Origin to reduce DNS-rebinding/browser-origin attacks. However, loopback is **not per-user authentication**. Another process with access to the same machine may be able to call the server while it is running.

Policy:

- prefer stdio for normal local clients;
- use HTTP only on a trusted single-user machine;
- never expose v1 HTTP to LAN/public interfaces;
- a remote/hosted connector requires real authentication/authorization and a separate design review.

### SR-05 — terminal-control injection

Externally controlled Ufora/upstream text can contain C0/C1 control bytes, including terminal escape sequences. Captured subprocess output and structured direct-course data are now recursively sanitized before they reach human terminal rendering. New tests cover ESC/BEL payloads.

### SR-06 — bounded HTTP waits

Subprocess-backed API operations already had a 90-second execution timeout. Direct material calls now apply a 30-second default `requests` timeout unless a caller supplies a stricter one, preventing an indefinitely stuck MCP/CLI request on a stalled connection.

### SR-07 — read-only MCP semantics

The underlying authentication helper can attempt a local headless browser-session refresh when a short-lived Brightspace token expires. That would rewrite local token/session state even though the requested MCP operation is advertised as read-only.

1.0.1 disables that silent refresh inside the MCP server (`D2L_NO_AUTO_LOGIN=1`). An expired MCP session now fails and requires the student to run `ufora login` explicitly. This makes the MCP `readOnlyHint=true` materially more accurate: tool calls do not mutate Ufora course data and do not silently rewrite credential state as an authentication side effect. The annotation remains a client hint rather than an enforcement mechanism; the actual guarantee comes from the server implementation.

### SR-08 — dependency / CI supply chain

The security-sensitive Brightspace/authentication layer comes from pinned `d2l-cli==0.2.2` rather than being owned entirely by this repository. This is disclosed to UGent and should be included in institutional review.

Current controls:

- all direct runtime dependencies are exactly pinned in package metadata, including `d2l-cli`, the MCP SDK, Playwright, Requests, and the PDF/font parsers;
- `uv.lock` contains registry artifact hashes for resolved runtime/test dependencies used by frozen source-checkout/CI installs;
- the Hatchling build backend is exactly pinned instead of floating during package builds;
- CI installs runtime/test dependencies from the frozen lockfile;
- GitHub Actions are pinned to full commit SHAs;
- Ruff, pytest, Bandit medium+ scanning, and `pip-audit` run in CI;
- Dependabot is configured weekly for Python dependencies and GitHub Actions.

Longer-term, official UGent OAuth or bringing the minimum required authentication/client code under this project's direct maintenance would reduce this trust dependency.

### SR-09 — parser/resource exhaustion

Direct material extraction rejects content larger than 50 MiB after receipt and caps returned text length. Network calls are timeout-bounded and no active document/macros/scripts are executed.

Residual risk: a highly compressed or pathological PDF within the size limit can still make `pypdf` consume substantial CPU/RAM. If this becomes a multi-user or institution-managed service, parsing should move into a resource-limited subprocess/container and downloads should be streamed with a hard byte cap rather than fully buffered first.

### SR-10 — secrets and release artifacts

The review found no high-confidence GitHub/OpenAI-style tokens, JWTs, private keys, `.d2l` state, or token files in the reviewed Git history or built 1.0.2 artifacts. `.gitignore` now explicitly excludes `.env*` (except an intentional example), `.d2l/`, and `token.json` in addition to normal build/virtualenv files.

### SR-11 — ambient credential inheritance

The generic upstream token loader supports development-friendly fallback sources: a `D2L_TOKEN` environment variable and a cwd `.env` file. For Ufora AI that flexibility is undesirable. If the dedicated local token were missing or expired, the effective Brightspace identity could otherwise depend on the shell environment or directory from which the student launched the command, and `ufora logout` would not deterministically disconnect the public integration.

1.0.1 patches token loading so the public CLI/MCP accept only the fixed local `~/.d2l/token.json` state created by `ufora login`. Child processes also have `D2L_TOKEN` stripped from their environment. Regression tests verify that an ambient environment token is ignored, a valid saved token is accepted, and an expired saved token is rejected. This is an authentication-integrity hardening rather than a demonstrated credential-exfiltration path: Ufora AI already forces API traffic to the UGent Ufora host.

### SR-12 — cloud AI data residency / institutional data handling

UGent's current student security guidance says students must not store confidential information—including personal data—on cloud services with data storage outside the EEA. Ufora's own privacy statement confirms that Ufora processes personal user/content/action data. Ufora AI itself has no cloud backend, but an MCP client can receive grades, announcements, course material, identity data, and other Ufora output and may then transmit/store that data in its own cloud environment.

This creates a **deployment-policy boundary, not a local-server code bug**. The local CLI and a fully local AI client keep the Ufora AI processing path on the student's machine. A cloud AI client must be evaluated separately for data residency, retention, training/use, access controls, and contractual terms.

For ChatGPT specifically, OpenAI currently documents European data residency for eligible ChatGPT Enterprise/Edu workspaces and eligible API customers; ordinary personal ChatGPT accounts should not be assumed to provide the same residency guarantee. Even residency-enabled AI deployments still need UGent approval for the intended categories of Ufora data and use case.

Institutional recommendation: do not pitch v1 as “connect your personal ChatGPT account to all of Ufora.” Pitch the open-source local CLI/MCP first, and ask UGent which AI environments/data categories they are willing to approve. If UGent wants a ChatGPT workflow, a managed ChatGPT Edu/approved environment with appropriate European residency and governance is a much cleaner target than arbitrary personal accounts.

### SR-13 — course-material permission / copyright boundary

UGent's current GenAI guidance says course materials are **not automatically permitted to be uploaded to an AI system**. Course materials may be copyrighted and may not belong to the student; UGent says they should only be uploaded when the student has permission or when the lecturer has made them available through an approved AI system.

This matters directly to Ufora AI because `read_course_material` can return slides, PDFs, syllabi, and substantial module text to an MCP client. If that client is cloud-hosted, the material leaves the student's device for AI processing even though Ufora AI itself has no backend. Local retrieval is not itself permission to redistribute or disclose the material to another service.

Controls and policy:

- Ufora AI never uploads course files on its own; disclosure occurs only when the chosen MCP/AI client requests and receives tool output;
- the bundled agent guidance requires data minimization and treats cloud transmission of full course material as permission-sensitive;
- a local CLI or fully local AI client avoids this third-party disclosure boundary, although ordinary copyright/use restrictions still apply;
- an institutionally promoted cloud-AI workflow should define which materials may be transmitted and how lecturer/rightsholder approval is represented.

Residual risk is governance-dependent and cannot be solved by code alone. For UGent review, this should be a first-class question alongside OAuth and data residency rather than buried in a general disclaimer.

References used for this review:

- UGent student security guidance: <https://helpdesk.ugent.be/security/veilig-werken-studenten.php>
- UGent Ufora privacy statement: <https://www.ugent.be/student/en/ict/educational-tools/ufora/privacystatement>
- UGent student GenAI guidance: <https://www.ugent.be/student/en/study-support/genai>
- OpenAI ChatGPT data residency documentation: <https://help.openai.com/en/articles/9903489-data-residency-for-chatgpt>

## Positive controls verified

- Ufora host is forced to `https://ufora.ugent.be` for the public integration path.
- No shell interpolation: subprocesses use argument arrays.
- No `eval`, `exec`, pickle loading, archive extraction, disabled TLS verification, or runtime arbitrary URL fetch was found in project source.
- Reviewed Brightspace client data methods are GET/read operations.
- MCP exposes no assignment submission, discussion posting, grade mutation, or content-mark-read tools.
- Non-loopback HTTP MCP binding is rejected.
- Browser Origin rejection is covered by a live Starlette/MCP test.
- Material reads cap returned characters and binary extraction is bounded by a 50 MiB application limit.
- Package artifacts contain only expected package/metadata files and no sensitive local auth paths.

## Verification performed

At the end of the review pass on macOS:

```text
uv lock --check                    PASS
uv sync --frozen --extra dev       PASS
pytest                              68 passed
ruff 0.16.7                         PASS
bandit 1.9.4 medium+                0 findings
pip-audit 2.10.1                    no known dependency vulnerabilities
uv build                            wheel + sdist PASS
Git-history secret pattern scan     no high-confidence secrets found
release artifact sensitive scan     no credential/auth-state files found
```

One Starlette/AnyIO deprecation warning appears in the HTTP test dependency stack; it is not a security failure and should be removed naturally by future compatible dependency updates.

## Before contacting UGent

### Required

- release the final reviewed state as **1.0.2** so the public code and institutional-policy claims match;
- link UGent reviewers directly to this document, `SECURITY.md`, `PRIVACY.md`, and `docs/FOR-UGENT.md`;
- describe the project as a **candidate for review/pilot**, not an approved service;
- explicitly ask UGent whether the current local token mechanism is acceptable or whether they want a registered OAuth client;
- explicitly ask which AI clients/data-residency configurations are acceptable for Ufora personal/confidential data; do not assume personal cloud-AI accounts are approved;
- explicitly ask under what conditions course materials may be passed to AI clients and how lecturer/rightsholder approval should be represented.

### Strongly recommended repository governance

- require the CI workflow before merging to `main` once GitHub branch protection/rulesets are configured;
- enable Dependabot alerts and security updates in repository settings in addition to the committed version-update config;
- enable private vulnerability reporting if available for the repository;
- prefer pull requests for future security-sensitive authentication/MCP changes, even as a single maintainer.

## Release gate

The code-level hardening through 1.0.2 passes the current review gate. The **remaining blockers for an institutional “secure/endorsed” claim are governance decisions around authentication, downstream AI-client/data-residency handling, and course-material permissions—not a known unpatched remote-code-execution or credential-exfiltration bug in Ufora AI itself**.
