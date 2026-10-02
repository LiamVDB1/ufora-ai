# Ufora AI

[![CI](https://github.com/LiamVDB1/ufora-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/LiamVDB1/ufora-ai/actions/workflows/ci.yml)

> Unofficial, student-built, read-only CLI and MCP integration for **UGent Ufora** (D2L Brightspace).

Ufora AI lets students access their own Ufora data from a terminal or an MCP-compatible AI client without screen scraping. It can list courses, read complete announcements, inspect deadlines and grades, browse course structure, and retrieve the actual text from PDF course materials.

**Ufora AI is not affiliated with or endorsed by Ghent University or D2L.** Ufora and Brightspace are referenced only to identify the services this project interoperates with.

## Why this exists

Students already have the information they need in Ufora, but it is fragmented across announcements, course content, calendars, grades, files, quizzes, discussions, and external links. Ufora AI provides one read-only interface over that student-visible data so tools can answer questions such as:

- What courses do I have this academic year?
- What is due in the next two weeks?
- What did the professor announce?
- What grade did I receive?
- What material is inside this course?
- What does this lecture PDF actually say?

## Features

| Capability | CLI | MCP |
| --- | :---: | :---: |
| Current and historical courses | ✓ | ✓ |
| Dedicated Course Overview (requirements, exam/project rules, software) | ✓ | ✓ |
| Full announcement body text | ✓ | ✓ |
| Search across Overview, module bodies, topics, and descriptions | ✓ | ✓ |
| One-course context bundle | ✓ | ✓ |
| Calendar, due and overdue items | ✓ | ✓ |
| Grades and final grades | ✓ | ✓ |
| Assignments and quizzes | ✓ | ✓ |
| Discussion-forum metadata | ✓ | ✓ |
| Nested course-content tree | ✓ | ✓ |
| PDF/text material extraction | ✓ | ✓ |
| File/module download | ✓ | — |
| Broad AI-oriented snapshot | ✓ | ✓ |
| Local Streamable HTTP MCP | — | ✓ |
| Read-only by design | ✓ | ✓ |

The MCP surface intentionally does **not** submit work, post messages, edit grades, or mutate Ufora.

## Installation

Ufora AI requires Python 3.11+ and a Chromium-family browser for the initial login.

### With `uv` (recommended)

From a checkout:

```bash
uv tool install .
```

Install the audited release directly from the public repository:

```bash
uv tool install git+https://github.com/LiamVDB1/ufora-ai.git@v1.2.0
```

Use `@main` instead only if you deliberately want unreleased development changes.

### Development install

```bash
git clone https://github.com/LiamVDB1/ufora-ai.git
cd ufora-ai
uv sync --extra dev
uv run pytest
```

## Login

```bash
ufora login
```

When this machine has signed in before, `ufora login` first reuses that sign-in without a window, clicking the "Ufora login" link and your signed-in Microsoft account for you (see [Staying signed in](#staying-signed-in)). This also works over SSH. Only when UGent needs you, for example for a password or a choice between accounts, does it say why and open a browser window. `ufora login --interactive` skips the silent attempt.

In the browser window, log into UGent exactly as you normally would. The underlying `d2l-cli` flow uses a dedicated local browser profile and, after UGent SSO has completed, retrieves a Brightspace web access token from that authenticated browser session. Ufora AI stores the resulting session material under `~/.d2l/` and never receives your UGent password. The public Ufora AI client intentionally ignores ambient `D2L_TOKEN` environment values and cwd `.env` token fallbacks, so authentication cannot silently change based on the directory or shell environment in which you run it.

This is a pragmatic **local** login mechanism, not an OAuth application registered or endorsed by UGent. The student/course-data client only exposes GET/read operations; the separate login flow uses authentication requests to establish the session/token. The captured browser token must be treated as a sensitive credential. See [SECURITY.md](SECURITY.md) for the exact trust boundary.

### Staying signed in

Brightspace access tokens last about an hour. Ufora AI renews them from the saved sign-in without opening a window: the dedicated browser profile is reopened headlessly and Ufora's own session plus the UGent/Microsoft SSO session behind it are reused. Chromium drops such session cookies whenever a browser closes, so Ufora AI keeps a private copy of only the sign-in-chain cookies (`*.ugent.be`, `*.microsoftonline.com`) in `~/.d2l/session.json` (mode 0600) and restores it on the next launch.

Once Ufora's own session has timed out, that headless browser lands on UGent's sign-in landing page and then on Microsoft's account picker. Ufora AI clicks through exactly those two deterministic steps (the single "Ufora login" link, the single signed-in account, and "Stay signed in?" if asked). Anything that needs a person, such as a password prompt or a choice between accounts, makes the renewal fail loudly with the page it stopped on and the time of the last successful renewal.

The CLI renews an expired token automatically. MCP tools never touch credential state, so on a machine that serves MCP, keep the token fresh with an explicit renewal on a timer:

```bash
ufora refresh            # renew now; exits non-zero with "Run: ufora login" when the sign-in is gone
ufora refresh --debug    # same, tracing every page (no secrets) to ~/.d2l/debug/<timestamp>/
```

On Linux with systemd, install the bundled user timer (every 30 minutes; it also keeps Ufora's idle timeout from expiring):

```bash
mkdir -p ~/.config/systemd/user
cp contrib/systemd/ufora-refresh.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now ufora-refresh.timer
```

On a headless server, sign in on a machine with a screen (also running Ufora AI 1.2+) and move the sign-in over in one command. The bundle holds only the sign-in-chain cookies and the current token; the browser profile itself is not portable across operating systems because Chrome encrypts its cookie store per machine:

```bash
ufora session export - | ssh server '~/.local/bin/ufora session import -'
```

Import merges rather than replaces (newest cookie per domain and name, the longer-lived token), so it is safe to run again after a later login. `ufora session export bundle.json` writes a 0600 file instead when you prefer to copy it yourself; delete it afterwards, it grants access to your Ufora account.

You then only need `ufora login` again when UGent itself ends the sign-in (for example a forced re-authentication or password change).

Then verify the installation:

```bash
ufora doctor
ufora whoami
ufora courses
```

To disconnect this machine and remove the locally cached Brightspace token, the saved sign-in cookies, and the dedicated Ufora browser profile:

```bash
ufora logout
```

`ufora logout` removes Ufora AI's local authentication copies. It does **not** claim to revoke an already-issued Brightspace access token server-side; that token expires according to Brightspace's own lifetime.

Never paste your UGent password, bearer token, or browser cookies into Ufora AI, an issue report, or an AI conversation.

## CLI examples

```bash
# Current academic year
ufora courses

# Find a course by title/code/ID, including historical offerings
ufora courses Logisch

# Historical real course offerings too (groups such as GR01 remain excluded)
ufora courses --all

# Actual announcements across current courses (not Brightspace's separate Activity Feed)
ufora news

# Complete machine-readable announcements for one course
ufora --json news C003783A

# Course-level requirements/instructions (separate Brightspace Overview surface)
ufora overview C003783A

# One-course AI context bundle
ufora --json context C003783A

# Course data
ufora grades C003783A
ufora assignments C003787A
ufora quizzes E008620A
ufora discussions C003787A

# Search all important course-content surfaces
ufora search C003789A "haplotype"

# Rich nested content structure
ufora --json content C003783A --toc

# Read the actual body of an Overview, module page, inline topic, or PDF/text topic
ufora material C003789A "Project"
ufora material C003783A "Hoofdstuk 1"
ufora material C003783A "Slides / Tactics"

# Download a single content topic by title/path/ID, or recursively download a module
ufora download-content C003783A 3211795 -o ./materials
ufora download-content C003783A "Slides" -o ./slides

# Cross-course planning
ufora calendar --days 14
ufora due --days 14
ufora overdue

# AI snapshot
ufora --json dump --shallow
ufora --json dump --since 24
```

## MCP

Ufora AI ships a first-class MCP server as `ufora-mcp`.

### stdio

```bash
ufora-mcp
```

Generic MCP configuration:

```json
{
  "mcpServers": {
    "ufora": {
      "command": "ufora-mcp"
    }
  }
}
```

For Codex CLI:

```bash
codex mcp add ufora -- ufora-mcp
```

### Local Streamable HTTP

```bash
ufora-mcp --transport http
```

The endpoint is then:

```text
http://127.0.0.1:8765/mcp
```

You can customize the loopback port/path:

```bash
ufora-mcp --transport http --port 9000 --path /mcp
```

**v1 deliberately refuses non-loopback HTTP binding.** The local version reuses the student's local authenticated Ufora session; exposing that server to a network would create the wrong security model. Loopback is not per-user authentication, so **prefer stdio** when the client supports it and only use local HTTP on a trusted single-user machine. A future hosted integration should use official institution-approved OAuth instead.

See [`docs/MCP.md`](docs/MCP.md) for the tool/resource catalog and client guidance.

## Agent skill

The repository includes a companion agent skill that explains Ufora-specific behavior and good tool-selection patterns.

Install it to the common Agents skill location:

```bash
ufora skill install
```

Or inspect it:

```bash
ufora skill show
```

The MCP server also exposes the same guidance as the `ufora://guide` resource.

## UGent-specific compatibility

Ufora has a few behaviors that generic Brightspace tools can get wrong. Ufora AI handles these explicitly:

- UGent localizes the human-readable `Course Offering` type to **`Cursuseditie`**. Ufora AI uses Brightspace's stable machine-readable type code instead.
- UGent returns group enrollments such as **`C003783A GR01`** alongside courses. These are groups, not courses, and are excluded from course lists/resolution.
- Historical offerings can remain marked active for years. Cross-course queries therefore default to the **current academic year**, while `courses --all` remains available for history.
- Brightspace's **Course Overview is separate from the table of contents**. Ufora AI exposes it explicitly because it often contains required software, study material, grading rules, exam format, and project expectations.
- Module descriptions are first-class content too: professors can put an entire project brief, datasets, submission rules, or FAQ directly on a module such as `Project`, without creating a file/topic.
- Brightspace's user Activity Feed is not the same thing as course announcements and can be empty while courses have published News. `ufora news` therefore aggregates actual News from current courses instead of exposing that misleading feed.
- Some professors distribute work through GitHub, Dodona, external pages, or ordinary course content rather than Brightspace's Assignments feature. An empty Assignments endpoint does not prove that the course has no coursework.

The details and rationale are documented in [`docs/COMPATIBILITY.md`](docs/COMPATIBILITY.md).

## Privacy and security

Ufora AI v1 is local-first:

- no Ufora credentials are sent to a Ufora AI backend;
- there is no analytics or telemetry in this project;
- authentication state remains on the student's machine under `~/.d2l/`;
- Ufora requests go directly from the student's machine to `https://ufora.ugent.be`;
- MCP results go only to the MCP client the student chooses to run;
- a cloud MCP/AI client may then process or store those results off-device under its own terms, so client choice and data residency are a separate privacy boundary;
- UGent's current GenAI guidance says course materials are **not automatically permitted to be uploaded to an AI system**; permission or an approved AI setup may be required before sending retrieved course material to a cloud AI client;
- all student/course-data operations exposed by this project are read-only.

Read [`PRIVACY.md`](PRIVACY.md), [`SECURITY.md`](SECURITY.md), and the dated [`docs/SECURITY-REVIEW.md`](docs/SECURITY-REVIEW.md) before deploying or modifying the trust boundary. Do not assume that an arbitrary personal cloud-AI account is an institutionally approved destination for Ufora data or course material.

## Architecture

```text
                         ┌───────────────────────┐
                         │   MCP-compatible AI   │
                         └───────────┬───────────┘
                                     │ stdio / localhost HTTP
                                     ▼
┌──────────┐                 ┌───────────────────┐
│ Terminal │ ──────────────► │     Ufora AI      │
└──────────┘                 │ CLI + MCP + skill │
                             └─────────┬─────────┘
                                       │ read-only Brightspace API
                                       ▼
                             ┌───────────────────┐
                             │   UGent Ufora     │
                             │ D2L Brightspace   │
                             └───────────────────┘
```

Ufora AI currently builds on the MIT-licensed [`d2l-cli`](https://github.com/Aaryan-Kapoor/d2l-cli) project and applies a small UGent compatibility layer. The dependency is pinned in v1 so upstream changes cannot silently alter the behavior of a released version.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## For Ghent University

The project is intentionally designed so that UGent can review it without trusting a hosted third party. v1 runs locally, is read-only, contains no telemetry, and is open source.

A future one-click hosted ChatGPT/AI connector would need **official Brightspace OAuth plus an UGent-approved AI/data-residency and course-material permission model** rather than the local browser-session approach. That hosted version is intentionally outside v1's trust boundary and would only be pursued with institutional cooperation.

See [`docs/FOR-UGENT.md`](docs/FOR-UGENT.md) for the review/pilot proposal, [`docs/SECURITY-REVIEW.md`](docs/SECURITY-REVIEW.md) for the pre-outreach security review, and [`docs/DEMO.md`](docs/DEMO.md) for a short demonstration flow.

## Contributing

Contributions are welcome. In particular, useful areas include:

- accessibility and onboarding improvements;
- additional read-only Ufora surfaces;
- robust extraction for more educational file formats;
- tests for Brightspace localization/configuration edge cases;
- documentation for Linux/Windows environments;
- adapters for other institutions, once the common behavior is understood well enough to generalize cleanly.

Read [`CONTRIBUTING.md`](CONTRIBUTING.md) first. The project's read-only guarantee is a core design constraint.

## License

MIT. See [`LICENSE`](LICENSE).
