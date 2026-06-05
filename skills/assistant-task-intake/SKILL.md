# Assistant Task Intake

Use this skill before taking action in this repository. Its purpose is to make
the first move deliberate without slowing down obvious work.

## Intake Checklist

1. Read the user's latest request and identify the concrete outcome they want.
2. Check repository state before edits:
   - Run `git status --short`.
   - Prefer `rg` or `rg --files` for locating files and symbols.
3. If the request is clear, proceed without asking for confirmation.
4. Ask a question only when missing information would make a reasonable
   implementation risky or likely wrong.
5. Before editing files, state briefly what will change and why.
6. Keep changes scoped to the requested outcome and existing project patterns.
7. Verify with the narrowest meaningful command, then broaden only when the
   change touches shared behavior.
8. Report what changed, what was verified, and any remaining risk.

## Repository Defaults

- Preserve the local-first privacy boundary described in `README.md`.
- Do not broaden discovery or indexing to user content without explicit source
  authorization behavior and tests.
- Treat docs and registry records as governance surfaces: keep terminology,
  risk labels, and policy snapshots consistent when changing source behavior.
- Avoid packaging claims unless packaging metadata exists in the repository.
