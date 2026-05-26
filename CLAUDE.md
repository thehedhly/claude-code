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

## GitHub Interactions

**Never use the `gh` CLI for GitHub operations** (issues, pull requests, comments, labels, reviews, etc.). Always use the configured GitHub MCP server tools (`mcp__github__*`) instead. The MCP server is the authorised integration for this repo.

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

## Testing Approach

This repo uses **dependency-free smoke tests** — no pytest, no fixtures, no test framework. The reasons are deliberate:

1. **Hooks must work on every dev machine without `pip install`.** Anything that needs a Python package fails the moment a contributor's environment differs.
2. **A hook's only public interface is JSON in / JSON out via stdin/stdout.** Subprocess-based smoke tests exercise that interface end-to-end — exactly what a real session does.
3. **Test files must not trip the live hooks** when the user edits them. The `protect_secrets.py` hook scans `tool_input.command` strings; if a test file contains literal text like `AKIA…` or `BEGIN OPENSSH PRIVATE KEY`, the user's own session will block reading or editing the test file.

### Conventions

- **One smoke file per scope.** `tests/smoke_issue_<N>.py` for issue-driven PRs; `tests/smoke_<feature>.py` for cross-cutting features. Self-contained — each file invokes the hook script as a subprocess and asserts on `decision`.
- **Construct sensitive material dynamically.** Never let a real-looking secret pattern appear as a literal in the test file. Use `AKIA = "AKIA" + "IOSFODNN7EXAMPLE"`, `INJECT = "Ignore " + "previous instructions"`, etc. — concatenation defeats the regex scanners that run on the developer's own session.
- **Each case is a tuple**: `(name, payload_dict, env_extra_or_None, expected_decision)`. `expected_decision` ∈ {`"pass"`, `"warn"`, `"block"`}.
- **A `pass` is `stdout == ""` and `rc == 0`.** Anything else is a JSON object whose `decision` field is classified.
- **Include regression cases**, not just new coverage. Every new test file must re-exercise the prior behavior the change touches (Bash regression on `protect_secrets.py`, legacy-payload compatibility, etc.).
- **Run the full test suite before every commit and before opening a PR.** A new feature's tests passing isn't sufficient — existing tests must still pass.

### Running

```bash
# Single file
python3 tests/smoke_issue_3.py
python3 tests/smoke_issue_4.py

# All smoke files (manual loop — keep this trivial; no runner needed)
for f in tests/smoke_*.py; do python3 "$f" || echo "FAIL: $f"; done
```

A test file exits `0` on all-pass, `1` if any case failed.

## Issue-Driven Workflow

When the user asks "work on issue #N" (or equivalent — "implement #N", "fix #N", etc.), execute this workflow without asking for confirmation on the standard steps:

1. **Read the issue.** Use `mcp__github__issue_read` to fetch both the body and comments. Comments may contain refinements the original body lacks.
2. **Branch from `main`.** Name: `fix/issue-<N>-<short-slug>`. Always branch from the latest `main` (fetch + ff first); do not branch off another open feature branch.
3. **Follow the issue's "Potential solution" section as the design spec.** If it sketches code, table, or wiring — implement what's sketched, not an alternative. Deviations require an explicit reason called out in the PR description.
4. **Respect the issue's "Out of scope" section.** Do not bundle additional fixes into the PR even if they look adjacent — open a follow-up issue instead.
5. **Write tests before committing.** Cover both the new behavior and a regression check against the file(s) being modified. Run the full `tests/smoke_*.py` suite — every existing file must still pass.
6. **Commit in Conventional Commits format** (see [Conventions](#conventions)). Squash unrelated noise; one focused commit per logical change.
7. **Open the PR with `Closes #<N>`** in the body. PR description follows the structure used in PR #6: Summary, What changed (table), Design notes, Out of scope, Test plan checklist.
8. **Confirm before merging.** Don't merge automatically — even when CI is green, the user reviews.

If any step fails (tests broken, issue spec ambiguous, "Potential solution" doesn't actually solve the problem on closer reading), stop and surface the blocker to the user with a concrete recommendation. Don't paper over it.
