# CLI Reference & Model Selection

Quick reference for Claude Code slash commands, keyboard shortcuts, non-interactive mode, and choosing the right model for the task.

---

## Slash Commands

| Command | Purpose | When to use |
|---------|---------|-------------|
| `/hooks` | List active hooks and their event matchers | Verify hooks loaded after editing `settings.json` |
| `/mcp` | List connected MCP servers and the tools they expose | Before trusting any MCP tool call; review after adding a new server |
| `/config` | Open interactive settings editor | Change model, mode, or `effortLevel` without editing JSON manually |
| `/cost` | Show token usage and estimated cost for the current session | Budget checks; detect runaway context or tool-call loops |
| `/compact` | Summarize conversation and continue | Mid-task when the session is getting long — see [docs/context-management.md](context-management.md) |
| `/clear` | Wipe conversation history entirely | Pivoting to a new topic; starting fresh — see [docs/context-management.md](context-management.md) |
| `/memory` | Review and edit CLAUDE.md content loaded into context | Audit what `#` quick-add wrote; remove stale or sensitive notes |
| `/review` | Run a code review on the current diff | Pre-push sanity check before opening a PR |
| `/help` | List available commands | First stop when exploring |
| `/exit` | End the session cleanly | Always prefer over closing the terminal window mid-task |

---

## Keyboard Shortcuts

| Key | Effect |
|-----|--------|
| `Esc` | Interrupt the current tool execution — does **not** undo commands that already ran |
| `Ctrl+C` | Cancel the current prompt input |
| `Up arrow` | Navigate prompt history (most recent first) |

Platform caveat: shortcuts may behave differently on Windows/WSL2.

---

## Non-Interactive Mode (`--print`)

`--print` runs Claude Code as a one-shot CLI tool — no TUI, output goes to stdout, exits when done.

```bash
# One-off question
claude --print "What does this error mean: ECONNREFUSED 127.0.0.1:5432"

# Pipe a file through Claude
cat src/auth.ts | claude --print "summarize the auth flow in three bullets"

# Structured JSON output for scripts
claude --print --output-format json "list the exported functions in src/utils.ts"
```

**Key properties of `--print` mode:**

- **Hooks still run.** The security hooks in `~/.claude/settings.json` are active. The security floor is preserved.
- **Stateless.** No session is persisted between calls. Each `--print` invocation starts fresh.
- **No context compaction.** Context is bounded per call, making it suitable for automated and CI use cases.
- **Composable.** Output can be piped to `jq`, `grep`, or other tools.

---

## `--fast` Flag

Forces the Haiku model for the session, regardless of the `model` setting in `settings.json`.

```bash
claude --fast "rename all variables named `tmp` to `temp` in src/"
```

Use `--fast` for:
- High-volume scripted calls where Haiku's reasoning is sufficient
- Quick reformatting, renaming, or lookup tasks
- Cost-sensitive batch operations

Haiku is roughly **15–25× cheaper per token than Opus** at current pricing. Setting `--fast` in a scripted pipeline can significantly reduce costs on tasks that do not require deep reasoning.

---

## Model Selection

Set the default model in `settings.json`:

```json
{ "model": "sonnet" }
```

Valid values: `"haiku"`, `"sonnet"`, `"opus"` — or a full model ID for version pinning (e.g., `"claude-sonnet-4-6"` to lock to a specific release).

Override per-session without touching the file: `/config` → model.

### Decision Matrix

| Task | Model | `effortLevel` |
|------|-------|---------------|
| Reformatting, renaming, boilerplate generation | `haiku` | `low` |
| Routine feature work, debugging, writing tests | `sonnet` | `medium` |
| Complex multi-file refactors, API design | `sonnet` | `high` |
| Architecture decisions, unfamiliar codebases | `opus` | `high` |
| Security review, adversarial reasoning, threat modeling | `opus` | `max` |
| Automated CI / scripted pipelines | `haiku` or `sonnet` | `low` |

---

## `effortLevel`

Controls how much reasoning Claude applies before responding.

| Value | Effect |
|-------|--------|
| `"low"` | Fast, minimal reasoning — best for simple lookups and reformatting |
| `"medium"` | Balanced — the right default for most day-to-day work |
| `"high"` | Extended reasoning — use for complex tasks where accuracy matters more than speed |
| `"max"` | Maximum reasoning budget — reserve for security reviews and hard architectural decisions |

**High `effortLevel` on Haiku is mostly wasted** — the effort token budget exceeds what Haiku can usefully consume. Pair Haiku with `"low"` or `"medium"`.

Override per-session with `/config` → effort — no file edit required.

---

## `/cost` for Budget Awareness

Run `/cost` mid-session on long tasks to see token usage and estimated spend.

**Signs of a problem:**
- Cost spikes unexpectedly → check for a tool being called in a tight loop (`/hooks` can help identify if a hook is misfiring)
- Cost grows steadily without useful output → the context may be saturated; run `/compact` and continue

Combining `/cost` + `/compact` on long sessions keeps both quality and spend under control.

---

## Recommended Global Defaults

A sensible starting point for `~/.claude/settings.json` (adjust per project as needed):

```json
{
  "model": "sonnet",
  "effortLevel": "high",
  "permissions": {
    "defaultMode": "default"
  }
}
```

Reserve Opus and `"max"` effort for specific tasks via `/config` rather than setting them globally — the cost difference adds up quickly on high-volume sessions.
