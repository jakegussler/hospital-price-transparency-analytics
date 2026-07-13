# Claude Code

@AGENTS.md

`AGENTS.md` is the canonical shared project guide. Keep architecture, commands,
domain constraints, and verification rules there so Codex, Claude Code, Cursor,
and human contributors use the same contract.

## Claude-Specific Guidance

- Use the imported guide before non-trivial work; load deeper documents only
  when its routing rules make them relevant.
- Put personal or machine-specific preferences in ignored `CLAUDE.local.md`, not
  in this shared file.
- Do not duplicate shared project context here. Update `AGENTS.md` when a durable
  cross-tool rule changes.
