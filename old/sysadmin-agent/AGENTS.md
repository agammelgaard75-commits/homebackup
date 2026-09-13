# Sysadmin Agent Project

This folder is the working memory for Goose sysadmin sessions.

At session start:
1. Read this file.
2. Read `TASK.md`.
3. Read `NOTES.md`.
4. Read `RUNBOOK.md`.
5. Begin by gathering evidence with tools.

## Rules

- Use local shell/file tools only.
- Do not use web search.
- Do not make unrelated changes.
- Do not stop after one command unless the task is fully verified.
- Continue the loop until the success criteria in `TASK.md` are met.

## Required Flow

For every task:

1. Inspect current state.
2. Identify likely cause.
3. Read relevant config/logs.
4. Backup files before editing.
5. Apply smallest safe fix.
6. Validate syntax.
7. Restart/reload service only if needed.
8. Verify result.
9. Update `NOTES.md`.
10. Summarize briefly.

## Execution Policy

When a task can be completed using available tools:

- execute the required tools immediately
- do not ask for permission
- do not ask "Would you like me to proceed?"
- do not present plans before execution
- execute first
- report results afterward

Only ask for confirmation if:
- the operation is destructive
- data may be deleted
- system availability may be impacted

## Planning

Do not ask for approval after creating a plan.

If tools are available:
- execute the first step immediately
- continue until completion
- stop only when blocked

## Important

Tool output is not completion.

Completion requires verified success.
