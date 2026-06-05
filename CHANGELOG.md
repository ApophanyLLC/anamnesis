# Anamnesis Changelog

## 2026-06-04

- Implemented policy snapshot persistence in `sources.authorization.json` so source re-authorization compares concrete policy fields instead of only hash IDs.
- Added interactive policy diffs during `authorize` when registry policy changes are detected.
- Added explicit re-authorization choices for policy drift:
  - Accept the new policy, 
  - Keep legacy restrictions (skip newly added file types),
  - Cancel.
- Added per-source tracking of ignored files when legacy mode is selected and surfaced it via `status` and verbose search diagnostics.
