# AI-Assisted Development

This repository treats AI context as maintained engineering infrastructure. The
goal is to help a new developer use Codex, Claude Code, or Cursor productively
without loading multiple copies of the same project description or relying on
private chat history.

## Context Architecture

| Surface | Purpose | Context policy |
|---|---|---|
| [`AGENTS.md`](../../AGENTS.md) | Canonical project contract: architecture boundaries, commands, domain rules, and verification expectations | Shared by every tool; keep concise and current |
| [`CLAUDE.md`](../../CLAUDE.md) | Claude Code entry point | Imports `AGENTS.md` and contains only Claude-specific guidance |
| [`.cursor/rules/project-context.mdc`](../../.cursor/rules/project-context.mdc) | Cursor IDE project rule | Includes the canonical guide instead of recreating it |
| `.agents/skills/` | Optional project-specific, repeatable workflows | Add only when a workflow needs progressive disclosure, scripts, or references |
| CI, tests, and linters | Mechanical enforcement | Prefer executable checks over asking an agent to remember enforceable rules |

Codex documents `AGENTS.md` as durable repository guidance and recommends skills
for richer reusable workflows. Claude Code supports importing `AGENTS.md` from a
small `CLAUDE.md`. Cursor project rules are version-controlled MDC files under
`.cursor/rules/` and can reference repository files. The adapters in this
repository follow those vendor-supported conventions.

## Design Principles

- **One source of truth.** Shared rules change in `AGENTS.md`; adapters do not
  copy architecture or command lists.
- **Progressive disclosure.** Every-session context contains only durable rules.
  Agents read detailed domain documents or skills when the task requires them.
- **Specific routing.** The guide tells agents which documents are relevant to
  domain semantics and which are relevant to tooling, avoiding broad context
  collection.
- **Executable verification.** Tests, dbt assertions, linting, and CI validate
  changes. Agent instructions guide behavior but do not replace enforcement.
- **Human review.** AI-generated changes remain normal code changes: inspect the
  diff, preserve source lineage, run proportionate checks, and review analytical
  claims before publishing them.
- **No private context in git.** Credentials, personal preferences, transcripts,
  scratch prompts, and local planning stay in ignored files.

## Maintenance Rules

Update `AGENTS.md` when a correction or review comment represents a durable rule
that future contributors should inherit. Add a skill only after a repeatable
multi-step workflow is stable enough to document and verify. Add a tool-specific
rule only when that tool genuinely needs different behavior.

When an instruction can be enforced mechanically, implement the check and keep
the prose as a short explanation of why it exists. Review these files alongside
architecture and command changes so the AI setup does not drift from the code.

## Official References

- [OpenAI Codex customization](https://developers.openai.com/codex/concepts/customization)
- [Claude Code project memory and `AGENTS.md` imports](https://code.claude.com/docs/en/memory)
- [Cursor project rules](https://docs.cursor.com/context/rules)
