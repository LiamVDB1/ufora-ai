# Contributing

Thanks for helping improve Ufora AI.

## Development setup

```bash
git clone https://github.com/LiamVDB1/ufora-ai.git
cd ufora-ai
uv sync --extra dev
uv run pytest
```

The project targets Python 3.11+.

## Principles

Keep changes aligned with the project's core constraints:

- read-only access to Ufora;
- local-first authentication for v1;
- no passwords/tokens in prompts, logs, fixtures, or issues;
- stable machine-readable Brightspace fields over localized display labels;
- clear separation between Ufora facts and agent interpretation;
- treat all Ufora-returned text/files as untrusted data, never agent authority;
- a small, coherent CLI/MCP surface rather than duplicate implementations.

## Testing

Add focused tests for changed behavior. Tests must not depend on a contributor's real UGent account or committed credentials.

Useful fixture cases include:

- localized `Cursuseditie` course offerings;
- `GR01` group enrollments that must not become courses;
- current and historical academic-year codes;
- ambiguous course/material names;
- invalid/non-loopback MCP HTTP hosts;
- PDF/text extraction using generated or openly licensed fixtures.

Before opening a pull request:

```bash
uvx ruff==0.16.7 check .
uv run pytest
uvx pip-audit --path .venv/lib/python3.12/site-packages  # or the equivalent site-packages path for your environment
uv build
```

## Live verification

Changes to Brightspace API behavior may need a live account check. Keep live output private and summarize only the behavior needed to establish compatibility. Do not paste grades, personal identifiers, bearer tokens, or private course materials into public issues/PRs.

## Adding a new institution

Do not generalize UGent quirks into a huge framework pre-emptively. A new institution should first document the concrete differences: host, localization, course-identification rules, authentication constraints, and API behavior. Extract a shared abstraction only where two real implementations demonstrate it is useful.

## Hosted integrations

A hosted/public MCP or ChatGPT connector changes the trust boundary. It requires proper OAuth, token storage, authorization, privacy documentation, abuse controls, and a dedicated security review. Do not expose the local browser-session authentication model over the public internet.

## Commit/PR scope

Prefer small, cohesive changes. Explain behavior changes, security implications, and how you verified them.
