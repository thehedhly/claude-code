# Security Checklist

Use this checklist when setting up Claude Code on a new machine, starting work in a sensitive repo, or onboarding a team member.

---

## Initial Setup

- [ ] Hooks installed: `~/.claude/hooks/protect.py`, `protect_secrets.py`, `protect_output.py`, `hook_logger.py`
- [ ] Hooks wired in `~/.claude/settings.json` under `PreToolUse[Bash]` and `PostToolUse[Bash]`
- [ ] Hook smoke tests pass (see [hooks.md — Debugging](hooks.md#debugging))
- [ ] `permissions.defaultMode` is set to `default` in global settings
- [ ] Hook log directory is writable: `~/.claude/hooks/logs/`

---

## Per-Session: Before Starting

- [ ] Confirm hooks are active — run `/hooks` in Claude Code
- [ ] Confirm permission mode is appropriate for this environment
- [ ] Check that `~/.claude/settings.json` contains no hard-coded credentials or tokens
- [ ] If using MCP servers, run `/mcp` and verify the tool list looks correct

---

## Project Configuration

- [ ] `.claude/settings.local.json` is listed in `.gitignore`
- [ ] `.env` and `*.env` variants are listed in `.gitignore`
- [ ] No API keys, tokens, or passwords appear in `CLAUDE.md` or `.claude/settings.json`
- [ ] MCP servers (if any) are scoped to project-level config, not global
- [ ] The project's `settings.json` does not downgrade the global permission mode without a documented reason

---

## Credential Hygiene

- [ ] Use short-lived credentials (STS, Workload Identity, OIDC) instead of long-lived keys where possible
- [ ] Do not paste credentials into a Claude Code prompt — set them as environment variables instead
- [ ] Rotate any credentials that were exposed in a Claude Code session (appeared in tool output, shared in chat)
- [ ] `~/.ssh/` permissions are `700` for the directory and `600` for key files
- [ ] `~/.aws/credentials` is `600`

---

## Git Safety

- [ ] Never use `git push --force` — use `git push --force-with-lease`
- [ ] Never skip git hooks with `--no-verify` unless you understand exactly what hooks do
- [ ] Never commit `.env`, credential files, or private keys — `protect_secrets.py` guards commands, but git is out of scope; use `git-secrets` or `gitleaks` for commit-time scanning
- [ ] Use signed commits for infrastructure and security-sensitive repos

---

## MCP Server Safety

- [ ] All MCP servers use pinned versions (no `@latest`)
- [ ] Credentials passed to MCP servers use `env`, not `args`
- [ ] Network-capable MCP servers have been reviewed for outbound connections
- [ ] For high-security sessions: deny all MCP tools with `"deny": ["mcp__*"]`

---

## Ongoing

- [ ] Review the audit log periodically for unexpected blocks:
  ```bash
  tail -50 ~/.claude/hooks/logs/security-hooks.jsonl | python3 -m json.tool
  ```
- [ ] Update hook detection patterns when new secret formats are encountered (new cloud provider keys, new token formats)
- [ ] Re-run this checklist after upgrading Claude Code (`claude --version`)

---

## Incident Response

If you suspect a session behaved unexpectedly (Claude accessed a file it shouldn't have, an MCP tool called an unexpected endpoint, etc.):

1. End the session immediately: `/exit`
2. Check the audit log: `~/.claude/hooks/logs/security-hooks.jsonl`
3. Check Claude Code's session history: `~/.claude/history.jsonl`
4. Review any files modified during the session with `git diff` or file timestamps
5. Rotate any credentials that were in scope during the session
6. Report unexpected behavior at https://github.com/anthropics/claude-code/issues

---

## Prompt Injection Awareness

Claude Code reads files, web pages, and command outputs — all of which can contain injected instructions. Signs of prompt injection:

- Claude performs actions you didn't request
- Claude references instructions you didn't give
- Unexpected tool calls appear in the session

If you notice any of these, end the session and audit the tool outputs that preceded the behavior. Do not resume in the same session.
