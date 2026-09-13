# Security policy

Ufora AI handles authenticated student data, so security boundaries are part of the product contract rather than an optional hardening step.

## Supported versions

Security fixes are applied to the latest `1.x` release. Older development builds are unsupported once a stable replacement exists.

## v1 trust boundary

Ufora AI v1 is designed for a **single local user**:

- Ufora authentication/session state stays under the user's local `~/.d2l/` directory.
- The CLI talks directly to UGent Ufora over HTTPS.
- MCP over stdio inherits the local user's permissions.
- Streamable HTTP is restricted to loopback addresses by the application.
- There is no hosted Ufora AI account, token database, telemetry service, or credential proxy in v1.
- Ufora-facing operations are read-only.

Do not remove the loopback restriction or add a network/public deployment mode without designing a real authentication and authorization layer. A hosted version should use institution-approved OAuth and must be treated as a separate trust boundary.

## Secrets

Never commit or report:

- `~/.d2l/token.json`;
- the `~/.d2l/browser_profile/` directory;
- Authorization headers or bearer tokens;
- UGent passwords, MFA material, cookies, or recovery codes;
- raw MCP transcripts containing private course/grade data unless the reporter has intentionally redacted them.

Ufora AI never needs a user's password as an application input.

## Untrusted content

Course names, announcement bodies, links, filenames, PDFs, and other Ufora content must be treated as untrusted input. The project avoids shell interpolation and invokes child processes with argument arrays. Downloaded filenames are sanitized by the underlying client and URL-decoded only after path removal.

PDF/text extraction is for student-authorized course material. Parsers should remain bounded and updated; do not add arbitrary code execution, macros, or active-document rendering to material extraction.

## Reporting a vulnerability

Please do not open a public issue containing exploit details, credentials, private student data, or tokens. Use the repository's private GitHub Security Advisory mechanism when the public repository is available.

A useful report includes the affected version, platform, reproduction steps using non-sensitive fixtures, impact, and a proposed mitigation if known.

## Security invariants for contributors

Changes must preserve these invariants unless a future major design explicitly replaces them:

1. Ufora-facing actions remain read-only.
2. Passwords/tokens are never requested through MCP tools.
3. Local HTTP does not bind to non-loopback interfaces.
4. User-controlled strings are never interpolated into shell commands.
5. Authentication material is not logged.
6. A hosted/public connector is not smuggled into the local trust model; it gets its own OAuth-backed design and review.
