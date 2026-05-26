# Context Management

Claude Code sessions have a finite context window. As a conversation grows, older content scrolls out of the effective window, response quality on complex tasks gradually degrades, and cost per turn increases. Managing context deliberately keeps sessions accurate and cost-efficient.

## Rule of Thumb

If you have been working actively in the same session for more than ~90 minutes, consider compacting or starting fresh.

---

## `/compact` — Summarize and Continue

Claude summarizes the full conversation into a concise context snapshot and replaces the history with that summary. The session continues without interruption.

**What is preserved:** The current working state — which files you discussed, what decisions were made, what is in progress.

**What is lost:** Exact tool outputs, verbatim earlier reasoning, specific error messages. The summary may drop nuance.

**Best practice:** Give Claude a one-line hint immediately before running `/compact`:

```
# The auth module must not be touched — migration is blocked until next sprint.
/compact
```

The `#` note is appended to CLAUDE.md and survives compaction. The hint text also appears in the PreCompact payload as `custom_instructions` (see [PreCompact hook](#precompact-hook)).

---

## `/clear` — Wipe and Start Fresh

Clears the entire conversation with no summary. Claude has no memory of the session afterward.

**Use when:**
- You finished a task and are pivoting to something completely unrelated
- The session went off track and you want a clean slate
- You are starting a new day and the previous context is stale

**Do not use mid-task** — use `/compact` instead to preserve working state.

---

## New Session Instead of `/clear`

When git state matters, prefer exiting and opening a new session over `/clear`:

1. Commit or stash all in-progress changes
2. `/exit` to end the session cleanly
3. Open a new Claude Code session
4. Let the fresh session load CLAUDE.md from scratch

This approach preserves a clean git history before the context wipe and avoids accidentally continuing work across an invisible session boundary.

---

## PreCompact Hook

The `PreCompact` hook fires just before Claude summarizes the conversation. It cannot block compaction — its purpose is to log or export session state before the history is replaced.

The hook receives on stdin:

```json
{
  "trigger": "manual",
  "custom_instructions": "Note that the auth module is off-limits."
}
```

`trigger` is `"manual"` (user ran `/compact`) or `"auto"` (Claude Code triggered it automatically when the context grew too large).

**Minimal logging snippet** — save as `~/.claude/hooks/precompact_log.py` and wire it as shown below. The same snippet is documented in [docs/hooks.md](hooks.md).

```python
#!/usr/bin/env python3
import json, sys
from datetime import datetime, timezone
from pathlib import Path

LOG_PATH = Path.home() / ".claude" / "hooks" / "logs" / "security-hooks.jsonl"

try:
    payload = json.load(sys.stdin)
except Exception:
    sys.exit(0)

try:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": "precompact",
        "details": {
            "trigger": payload.get("trigger"),
            "custom_instructions": payload.get("custom_instructions", ""),
        },
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
except Exception:
    pass

sys.exit(0)
```

Wire in `~/.claude/settings.json` (see `settings/settings.precompact.json.example` for the full config):

```json
{
  "hooks": {
    "PreCompact": [
      {
        "hooks": [
          { "type": "command", "command": "python3 /your/home/.claude/hooks/precompact_log.py" }
        ]
      }
    ]
  }
}
```

Note: `PreCompact` does not use a `matcher` field.

---

## Automated Pipelines

In non-interactive (`--print`) mode, each invocation is stateless — there is no persistent session to compact. Context is bounded per call. Use `--print` for scripted or CI use cases where session state does not matter. See [docs/cli-and-models.md](cli-and-models.md) for details.

---

## Decision Table

| Situation | Action |
|-----------|--------|
| Mid-task, conversation getting long | `/compact` with a hint |
| Task complete, pivoting to new topic | `/clear` or new session |
| Session went off the rails | `/exit` → review `git diff` → new session |
| Need to preserve a constraint through compaction | `# Add a note` first, then `/compact` |
| Automated/scripted use | `--print` (stateless per invocation) |
| Want to see why compaction triggered | Check audit log for `"event": "precompact"` with `"trigger": "auto"` |
