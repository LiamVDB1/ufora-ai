# Architecture

Ufora AI v1 is intentionally a **local integration**, not a hosted proxy.

## Components

```text
CLI user ───────────────┐
                        │
MCP client ─ stdio ─────┼──► Ufora AI ───► d2l-cli client ───► UGent Ufora
                        │       │
MCP client ─ localhost ─┘       ├── UGent compatibility layer
                                ├── material/PDF reader
                                └── bundled agent guide
```

### `ufora` CLI

The CLI provides human-readable and JSON/Markdown commands over the same Brightspace data used by MCP. It delegates generic Brightspace operations to the pinned `d2l-cli==0.2.2` dependency through `ufora_cli.d2l_entry`, which applies UGent-specific compatibility patches before command registration.

### UGent compatibility layer

`ufora_cli.d2l_entry` owns the concrete UGent differences discovered against live Ufora behavior:

- localized course-offering labels;
- group-vs-course disambiguation;
- current-academic-year selection;
- shallow snapshot behavior;
- filename decoding.

This is deliberately a thin adapter instead of a generic institution framework. If another institution is added later, shared behavior should only be extracted after the second implementation demonstrates a real common abstraction.

### Material reader

`ufora_cli.materials` resolves a topic from the Brightspace table of contents, retrieves student-authorized file content, and extracts text from PDFs/text-like files. Unsupported binary formats remain downloadable via the CLI rather than being rendered or executed.

### MCP server

`ufora-mcp` exposes read-only tools/resources using the official Python MCP SDK.

Two local transports are supported:

- **stdio** — preferred for local agents and CLI-configured clients;
- **Streamable HTTP on loopback** — useful for local clients that require an HTTP endpoint.

v1 rejects non-loopback HTTP hosts. This is a security boundary, not a missing convenience flag.

## Authentication

The initial login uses the underlying `d2l-cli` browser flow:

```text
student -> local browser -> UGent/Ufora SSO -> authenticated Brightspace session
                                              |
                                              v
                                       local ~/.d2l state
```

Ufora AI never accepts an UGent password as an application input. The browser is a dedicated local Chromium profile managed by the pinned `d2l-cli` login flow; after normal UGent SSO, that flow retrieves a Brightspace web access token from the authenticated session and stores it locally. Session/token material is treated as a credential. Ufora AI patches token loading so its public CLI/MCP use only that fixed `~/.d2l` state and do not inherit a `D2L_TOKEN` environment variable or cwd `.env` token fallback from the upstream generic client.

This is an unofficial local authentication mechanism, not a registered UGent OAuth client. The observed Ufora web token carries a broad `*:*:*` scope claim, so Ufora AI enforces read-only behavior in its GET-only student/course-data client and MCP tool surface rather than relying on token scope. The separate browser login helper uses authentication requests to establish the token. This is appropriate for the current local prototype/release boundary, but it is **not** the design to reuse for a hosted multi-user service.

## Hosted future architecture

A future hosted connector should be a separate deployable service/repository because it introduces a different trust boundary:

```text
ChatGPT / remote MCP client
          |
          v
hosted Ufora AI service
          |
          +-- its own user/session authorization
          +-- encrypted token storage
          +-- official Brightspace OAuth client
          |
          v
UGent Ufora
```

That version requires institution-approved OAuth registration, server-side authorization, privacy/security review, rate limiting, revocation, auditability, and operational ownership. It should not reuse the local browser-session mechanism.

## Why one repository for CLI + MCP

CLI and MCP share essentially every domain surface:

- authentication;
- course discovery;
- API compatibility;
- material reading;
- data models and semantics;
- tests and release lifecycle.

Splitting them in v1 would duplicate logic and create version skew. A separate repository becomes justified only when the hosted service introduces genuinely independent deployment and security concerns.

## Read-only invariant

The project intentionally exposes student-visible GET/read behavior. New write operations require a separate product/security decision and are out of scope for v1.
