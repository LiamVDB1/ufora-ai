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

Ufora AI never accepts an UGent password as an application input. Session/token material is local and treated as a credential.

This is appropriate for a local open-source tool, but **not** for a hosted multi-user service.

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
