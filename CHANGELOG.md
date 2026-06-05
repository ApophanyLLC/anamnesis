# Anamnesis Changelog

## 2026-06-05

- Added sync-time index health surfacing for schema drift-induced staleness:
  source-level warnings are persisted when disk content changed but indexing
  produces zero parsed documents within a >24h window.
- Added fallback parser visibility so search and status show `fallback_text` when
  plain-text parsing is used, with chunking context (`4000`-char windows with
  `250`-char overlap) included for transparent ranking expectations.
- Added `sync_warnings` tracking to source status records so search emits a one-line
  notice when sources are stale or impaired and keeps the warning in local
  diagnostics (`status`, `debug-report`, `privacy-audit --generate-report`).
- Added first-generation vendor parser-adapter registry and versioned policy
  snapshots. Parsing is now routed through adapter owners (`parser_documents`,
  `parser_copilot`) and documents can degrade to raw-text fallback mode when
  structured schema drift is detected, while preserving search/index continuity.

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
- Implemented proportional re-authorization friction:
  boundary-expanding policy updates still require confirmation; non-boundary
  policy drift updates now refresh authorization silently, and `authorize` now
  supports explicit `--auto-approve` / `--yes` for scripted non-interactive runs.
- Added per-source tracking of ignored files when legacy mode is selected and surfaced it via `status` and verbose search diagnostics.
- Added `debug-report` command and `privacy-audit --generate-report` to emit anonymized local diagnostics for user feedback without content.
- Added source-level cumulative error counters in the index manifest (`error_count` + `error_summary`) for local issue pattern tracking.
- Documented how to share debug reports as the project feedback loop.
