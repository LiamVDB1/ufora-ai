## What changed

Describe the user-visible behavior change.

## Why

What concrete Ufora/MCP/CLI problem does this solve?

## Verification

- [ ] `uv run pytest`
- [ ] `uv build`
- [ ] No credentials, private student data, grades, or proprietary course material added to fixtures/logs
- [ ] Read-only Ufora invariant preserved
- [ ] If MCP changed: stdio/local-HTTP behavior and agent guidance considered

## Security / privacy impact

Describe any change to authentication, token handling, network exposure, file parsing, or student-data flow. Write “none” only when the trust boundary is genuinely unchanged.
