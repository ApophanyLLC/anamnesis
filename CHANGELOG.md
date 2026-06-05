# Anamnesis Changelog

## 2026-06-04

- Implemented policy snapshot persistence in `sources.authorization.json` so source re-authorization compares concrete policy fields instead of only hash IDs.
- Added interactive policy diffs during `authorize` when registry policy changes are detected.
- Added explicit re-authorization choices for policy drift:
  - Accept the new policy, 
  - Keep legacy restrictions (skip newly added file types),
  - Cancel.
- Tightened re-authorization UX so policy changes are never auto-accepted:
  prompts now require explicit opt-in (default abort on Enter) and support
  explicit y/yes acceptance input.
- Added per-source tracking of ignored files when legacy mode is selected and surfaced it via `status` and verbose search diagnostics.
- Added `debug-report` command and `privacy-audit --generate-report` to emit anonymized local diagnostics for user feedback without content.
- Added source-level cumulative error counters in the index manifest (`error_count` + `error_summary`) for local issue pattern tracking.
- Documented how to share debug reports as the project feedback loop.
