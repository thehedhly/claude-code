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
- **Commit messages use [Conventional Commits](https://www.conventionalcommits.org/).** Format: `<type>(<scope>): <description>` — e.g. `fix(hooks): expand non-Bash matchers`. Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `ci`, `build`. Use `!` after the scope for breaking changes (e.g. `feat(hooks)!:`).

## GitHub Issue Format

**Title**: `[CRITICALITY] <concise summary>` — e.g. `[HIGH] Non-Bash tool matchers missing`. Criticality is `HIGH`, `MEDIUM`, or `LOW` based on blast radius and likelihood. Skip the prefix only when criticality genuinely doesn't apply (pure tracking issues, questions).

**Labels** (apply both — they answer different questions):
- **Criticality** (exactly one): `criticality:high`, `criticality:medium`, `criticality:low`.
- **Topical** (one or more): `security`, `hooks`, `prompt-injection`, `ux`, `docs`, `false-positive`, `mcp`, `installer`, etc. Create new labels only when an existing one doesn't fit.

**Body sections** (in this order; omit any that don't apply):

```markdown
## Description
What's wrong / missing. Lead with the concrete failure or bypass — show the actual command, payload, or scenario that demonstrates the gap. Quote relevant file:line references using markdown links (e.g. [`protect.py:36`](hooks/protect.py#L36)).

## Why this matters
One paragraph on real-world impact. Skip if obvious from Description.

## Potential solution
Concrete implementation sketch — code blocks, tables, regex patterns, settings.json snippets. Not "we should refactor X"; show the change. If multiple approaches exist, list them with trade-offs and recommend one.

## Out of scope
What you're explicitly not addressing here and which issue/PR tracks it. Prevents scope creep during implementation.

## Test additions
Concrete test cases the fix should add — input → expected outcome table works well.

---
Source: <where the finding came from — audit doc, PR review, surfaced during #N, etc.>
```

**Conventions inside the body**:
- Use markdown tables for enumerating patterns, paths, or matrix-style data.
- Use checklist syntax (`- [ ]`) only for test plans in PRs, not in issues.
- Reference other issues/PRs as `#N` — GitHub auto-links them.
- For findings that came from a structured audit (e.g. `Best-practice-audit-classified-by-criticality.txt`), include the source line in the footer so the issue is traceable back to the analysis.

**When closing**: use `state_reason: completed` (fixed), `not_planned` (won't do), or `duplicate` (link via `duplicate_of`). Never close without a reason.

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
