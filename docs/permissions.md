# Permission Modes

Claude Code runs in one of three permission modes, controlled by `permissions.defaultMode` in `settings.json`. The mode determines how much Claude can do without prompting you.

## Modes

### `default` (Recommended for most work)

Claude prompts before **every** tool call — reads, edits, shell commands, and MCP tools.

```json
{ "permissions": { "defaultMode": "default" } }
```

Use when:
- Working in production environments or repos with live credentials
- Exploring an unfamiliar codebase for the first time
- You want full visibility into every action

---

### `acceptEdits`

File reads and edits (`Read`, `Edit`, `Write`, `NotebookEdit`) are auto-approved. Shell commands (`Bash`) and MCP tools still prompt.

```json
{ "permissions": { "defaultMode": "acceptEdits" } }
```

Use when:
- You trust Claude's edits on a well-understood codebase
- You want to reduce prompt fatigue during pure refactoring or documentation sessions
- Shell commands should still require your explicit approval

---

### `bypassPermissions`

All tool calls run without prompting. No permission checks.

```json
{ "permissions": { "defaultMode": "bypassPermissions" } }
```

**Only use in:**
- Isolated CI/CD containers with no sensitive data or credentials
- Sandboxed ephemeral VMs destroyed after the run
- Automated pipelines with tightly scoped, short-lived credentials

**Never use on a developer workstation** with SSH keys, cloud credentials, production database access, or any persistent data.

---

## Settings Scoping

Settings merge in this order (later entries win for the same key):

```
~/.claude/settings.json              ← global, applies everywhere
<project>/.claude/settings.json      ← project-level, committed
<project>/.claude/settings.local.json ← personal override, git-ignored
```

Best practice: set the strictest default globally, loosen per project:

```json
// ~/.claude/settings.json
{ "permissions": { "defaultMode": "default" } }

// fast-iteration-project/.claude/settings.json
{ "permissions": { "defaultMode": "acceptEdits" } }
```

Add `.claude/settings.local.json` to your global `.gitignore` to prevent accidentally committing personal overrides with tokens or local paths.

---

## Per-Command Allowlists

Grant specific commands without changing the mode globally:

```json
{
  "permissions": {
    "allow": [
      "Bash(npm run test)",
      "Bash(git status)",
      "Bash(git diff)"
    ]
  }
}
```

Patterns support glob syntax. Allowlists are additive across scopes — project allows are appended to global allows.

Per-command deny list (blocks even in `acceptEdits`):

```json
{
  "permissions": {
    "deny": [
      "Bash(curl *)",
      "Bash(wget *)"
    ]
  }
}
```

---

## Hooks Are the Security Floor

**Hooks run regardless of permission mode.** Even in `bypassPermissions`, your `PreToolUse` hooks still execute and can block calls. This is why hooks belong in the global settings file — they provide a consistent safety floor across all projects and modes.

```
bypassPermissions  →  no prompts, but hooks still run
acceptEdits        →  no file-edit prompts, but hooks still run
default            →  prompts + hooks
```

If you need to temporarily disable a hook for a known-safe task, comment it out of `settings.json` and restore it immediately after.

---

## Choosing the Right Mode

| Situation | Recommended mode |
|-----------|-----------------|
| First time in a new codebase | `default` |
| Routine work on a personal project | `acceptEdits` |
| Automated CI with scoped ephemeral creds | `bypassPermissions` |
| Any session with production access | `default` |
| Security or infrastructure repos | `default` |
