# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

This repository is a reference implementation and documentation hub for setting up Claude Code securely, based on Anthropic's guidelines. It contains security hook scripts, settings templates, and detailed documentation.

## Layout

| Path | Purpose |
|------|---------|
| `install.py` | Automated installer — copies hooks and wires `settings.json` |
| `hooks/` | Security hook scripts — install to `~/.claude/hooks/` |
| `settings/` | `settings.json` example with all hooks wired |
| `docs/hooks.md` | Hook system reference, each script explained, PreCompact example, platform notes |
| `docs/permissions.md` | Permission mode selection guide |
| `docs/mcp.md` | MCP server setup and trust model |
| `docs/security-checklist.md` | Pre-flight security checklist |
| `docs/claude-md.md` | Memory hierarchy, what to put in CLAUDE.md, imports, `#` shorthand |
| `docs/context-management.md` | `/compact`, `/clear`, PreCompact hook, session hygiene |
| `docs/cli-and-models.md` | Slash commands, keyboard shortcuts, `--print`, `--fast`, model + effortLevel guide |

## Conventions

- All paths in scripts and docs must use `Path.home()` or `~/.claude/` — never hard-coded usernames.
- Hook scripts must exit `0` on pass-through; emit `{"decision": "block", "reason": "..."}` to stdout to block.
- `settings.json` does **not** expand `~` — `install.py` handles this; manual steps must use the full absolute path.
- When adding a detection pattern to a hook script, add a corresponding entry to `docs/hooks.md` and note whether the pattern is platform-specific.
- Validate any JSON snippet with `python3 -m json.tool` before committing.
- Several patterns in the hooks are **macOS-specific** (`diskutil`, `pbcopy`, `/dev/disk*`). See `docs/hooks.md — Platform Notes` when adapting for Linux or Windows/WSL2.

## Hook Contract

Claude Code passes tool context as JSON on stdin to each hook. For `PreToolUse[Bash]`:

```json
{ "tool_name": "Bash", "tool_input": { "command": "the shell command" } }
```

For `PostToolUse[Bash]`:

```json
{ "tool_name": "Bash", "tool_input": { "command": "..." }, "tool_output": "stdout/stderr text" }
```

A hook that prints `{"decision": "block", "reason": "..."}` and exits `0` blocks the call. A non-zero exit signals infrastructure failure and surfaces a warning without blocking.

## Testing Hooks Locally

```bash
echo '{"tool_input":{"command":"rm -rf /tmp/test"}}' | python3 hooks/protect.py
echo '{"tool_input":{"command":"cat ~/.ssh/id_rsa"}}' | python3 hooks/protect_secrets.py
echo '{"tool_output":"AKIA1234567890ABCDEF"}' | python3 hooks/protect_output.py
```

A blocked command prints `{"decision": "block", ...}`. A passing command prints nothing and exits `0`.
