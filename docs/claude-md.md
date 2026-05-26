# Writing Effective CLAUDE.md Files

CLAUDE.md is Claude Code's primary memory mechanism. It is loaded at session start and injects project context into every conversation without you having to re-explain it. A well-written CLAUDE.md saves time on every session; a poorly written one becomes stale noise or, worse, a security liability.

---

## Memory Hierarchy

Claude Code loads CLAUDE.md files in this order, merging them additively (lower layers append, they do not override):

```
~/.claude/CLAUDE.md                   ← personal global (never committed)
<project>/.claude/CLAUDE.md           ← project-level (committed, shared with team)
  └── @path/to/imported/file          ← files imported inside any CLAUDE.md
```

**Personal global (`~/.claude/CLAUDE.md`):** Your preferences, shortcuts, and personal workflow notes. Never commit this file. Put things here that apply across all your projects — your preferred git commit style, personal tool preferences, global reminders.

**Project-level (`.claude/CLAUDE.md` in the repo):** Team-shared context — build commands, architecture, conventions. Committed to version control. Treat it like documentation: everything written here is visible to every team member and to every Claude Code session on this project.

---

## What Belongs in CLAUDE.md

**Build and test commands** — the single highest-ROI entry. Without this, Claude runs `ls` and `cat package.json` at the start of every session to figure out how to run tests.

```markdown
## Commands
- Build: `npm run build`
- Test: `npm test` or `npx jest path/to/test.spec.ts`
- Lint: `npm run lint` (must pass before every commit)
```

**Architecture overview** — main entry points, data flow, what lives where. Two or three sentences is usually enough. Link to a design doc with `@` rather than pasting it.

**Coding conventions not obvious from the code** — naming patterns, error handling contracts, required patterns that linters don't enforce. If a new team member would ask "why does this work this way?" it belongs here.

**Known landmines** — files not to touch, deprecated modules still in use, infra quirks. These prevent Claude from making changes that are technically correct but operationally dangerous.

```markdown
## Off-Limits
- `src/legacy/payments/` — deprecated; do not modify. Migration tracked in ADR-012.
- Database migrations must be run as the `app` OS user, not root.
```

---

## What Does NOT Belong in CLAUDE.md

**Credentials, tokens, and API keys** — even "dev" secrets. Everything in CLAUDE.md ends up in Claude's context window, in session logs, and potentially in compaction summaries. Credentials here are effectively plaintext on disk.

**Volatile content that changes every sprint** — stale CLAUDE.md content is worse than no content because Claude will act on outdated information confidently. If something changes frequently, link to the live source instead.

**Content already obvious from the code** — do not describe what `userService.getById()` does. Well-named identifiers are self-documenting. CLAUDE.md should capture the *why* and the *gotchas*, not re-describe the *what*.

**Large prose blocks** — if a section is longer than ~20 lines, put it in a separate file and import it with `@`.

---

## `#` Quick-Add Shorthand

During a session, prefix any message with `#` to instantly append it to the project CLAUDE.md:

```
# The DB migration scripts must be run as the `app` user, not root.
```

Claude appends the text to `.claude/CLAUDE.md` immediately, with no confirmation step. This is useful for capturing a discovery mid-session before you forget it.

**Review with `/memory` after using it** — the `/memory` command shows the full content of loaded CLAUDE.md files so you can verify what was added and remove anything that should not persist.

---

## `@path/to/file` Imports

Any line in a CLAUDE.md that starts with `@` imports that file's content at session load time:

```markdown
## Architecture
@docs/architecture.md

## Active ADRs
@docs/ADR/
```

Use imports to:
- Keep CLAUDE.md short by referencing already-maintained documentation instead of duplicating it
- Split a large CLAUDE.md into topic files for easier editing

**Example composed structure:**

```
.claude/
  CLAUDE.md          ← imports below, plus a few top-level lines
  commands.md        ← build, test, lint commands
  architecture.md    ← system overview
docs/
  ADR/               ← decision records imported wholesale
```

**Security note:** Imports are resolved at session start. An `@` path that points to an externally generated, fetched, or user-controlled file is a potential prompt injection vector — an attacker could craft file content to redirect Claude's behavior. Audit every `@` import path, especially any that reference files outside the repo or generated during a build.

---

## Starter Template

Copy this to `<project>/.claude/CLAUDE.md` and trim to fit:

```markdown
# CLAUDE.md

## Purpose
One or two sentences describing what this project does and its primary language/stack.

## Commands
- Build: `<build command>`
- Test: `<test command>` | Single test: `<test command> path/to/test`
- Lint: `<lint command>` (required before commit)
- Dev server: `<dev server command>`

## Architecture
Brief description of the main entry points and data flow. Keep to 3-5 sentences.
Link to a design doc: @docs/architecture.md

## Conventions
- List non-obvious conventions here (naming, error handling, etc.)

## Off-Limits
- List files or modules that must not be modified and why.

## Notes
- Any other gotchas or reminders relevant to working in this codebase.
```

Keep the file under ~200 lines. Beyond that, move content into imported files.
