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
- assignments, quizzes, discussion-forum metadata, deadlines, and calendar events;
- files you explicitly ask it to read or download.

This processing occurs on your machine in v1.

## MCP clients

An MCP client can receive whatever data you ask Ufora AI to return. The privacy policy and data handling of that client are separate from this project. Before connecting an AI client, understand where that client sends and stores tool results. In particular, a cloud-hosted AI client may send requested course content, grades, identity data, or other tool output off your device under that provider's own terms even though Ufora AI itself has no backend.

UGent's current student IT-security guidance says not to store confidential information (including personal data) on cloud services whose data storage is outside the EEA. Ufora data can contain personal/confidential information, so **do not assume that an arbitrary personal cloud-AI account is an institutionally acceptable destination for Ufora data**. A local AI client avoids that cloud-storage boundary; an institutionally promoted cloud-AI setup should be reviewed by UGent for data residency, retention, access, and contractual terms.

UGent's current GenAI guidance adds a separate copyright/permission boundary: course materials are not automatically permitted to be uploaded to an AI system because they may be copyrighted and may not belong to the student. Permission from the rightsholder/lecturer or use through an approved AI setup may therefore be required before an MCP client sends retrieved slides, PDFs, syllabi, or other course material to a cloud AI provider. Using Ufora AI locally does not by itself grant that permission.

For ChatGPT specifically, European data residency is currently an organizational feature for eligible Enterprise/Edu workspaces (and eligible API customers), not something this project can guarantee for a student's personal account. The appropriate ChatGPT deployment for an UGent-backed workflow should therefore be decided with UGent rather than inferred by Ufora AI.

Ufora AI does not silently send your Ufora data to an AI provider. The MCP client decides when to call tools and how to use their output.

## Credentials

Treat `~/.d2l/` as sensitive. It can contain bearer-token/session material and an authenticated browser profile. Ufora AI attempts to apply private filesystem permissions where supported.

Run `ufora logout` to remove the cached token and dedicated browser profile from the local machine when you no longer want the integration connected. This removes local copies; it is not represented as a server-side Brightspace token revocation.

Do not upload this directory to issue trackers, cloud drives, public repositories, or debugging services.

## Hosted future versions

A future hosted connector would have a materially different privacy model because it would need institution-approved OAuth and server-side token handling. Such a service is not part of v1 and should ship with a separate privacy review and disclosure before any student uses it.
