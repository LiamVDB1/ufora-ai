# Privacy

Ufora AI v1 is intentionally local-first and has no application backend.

## Data flow

When you use the CLI or MCP server:

1. authentication is performed in your local browser against UGent/Ufora;
2. the resulting Brightspace session material is stored locally by the underlying `d2l-cli` flow under `~/.d2l/`;
3. API requests go directly from your machine to `https://ufora.ugent.be`;
4. results are printed locally or returned to the MCP client you chose to run.

Ufora AI itself does not operate an analytics, telemetry, crash-reporting, account, or cloud-storage service.

## What may be processed locally

Depending on the command/tool you invoke, Ufora AI may process:

- your name/user identity returned by Brightspace;
- enrolled course metadata;
- announcements and course content;
- grades and feedback;
- assignments, quizzes, discussions, deadlines, and calendar events;
- files you explicitly ask it to read or download.

This processing occurs on your machine in v1.

## MCP clients

An MCP client can receive whatever data you ask Ufora AI to return. The privacy policy and data handling of that client are separate from this project. Before connecting an AI client, understand where that client sends and stores tool results.

Ufora AI does not silently send your Ufora data to an AI provider. The MCP client decides when to call tools and how to use their output.

## Credentials

Treat `~/.d2l/` as sensitive. It can contain bearer-token/session material and an authenticated browser profile. Ufora AI attempts to apply private filesystem permissions where supported.

Do not upload this directory to issue trackers, cloud drives, public repositories, or debugging services.

## Hosted future versions

A future hosted connector would have a materially different privacy model because it would need institution-approved OAuth and server-side token handling. Such a service is not part of v1 and should ship with a separate privacy review and disclosure before any student uses it.
