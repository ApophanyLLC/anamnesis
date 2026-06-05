---
title: IDE Extensions (Phase 5 Optional)
doc_id: DOC-APP-ANAMNESIS-IDE-EXTENSIONS-001
type: proposal
status: planning
authority: informative
audience:
  - maintainer
scope:
  - project
  - repo-tools
verification: none
stability: experimental
owner: athame
reviewers:
  - maintainer
last_reviewed: '2026-06-04'
code_anchor: []
related_docs: []
supersedes: []
superseded_by: null
machine_summary: Documents IDE extension design direction without bundling implementation.
human_summary: Captures a minimal, privacy-preserving plan for optional editor
  integration as a later phase.
---

## Goal

Create editor/IDE context-aware search against local Anamnesis indexes without
relaxing local-first privacy boundaries.

## Recommended design constraints

- Keep authorization and parser pipelines CLI-driven and local to Anamnesis.
- IDE extensions should query only already-indexed local data via a local API boundary
  (future: authenticated local socket or local CLI bridge).
- Never grant automatic credentials flow; no vendor account tokens or cloud crawl.
- Never send indexed content to remote services.
- Explicitly surface sync health state so developers know whether results are stale or
  incomplete.

## Suggested phase-1 plan

- Read-only extension command palette action:
  - query term → display top local matches
  - open result path / source metadata
- Optional settings:
  - result limit
  - include raw-text mode results
  - open local source when multiple matches are found
- Reuse existing parser and policy boundaries; no extension-only bypass.

## Security posture

Treat this as optional convenience only. If an extension is disabled or unavailable,
users continue with existing CLI workflows without any functional dependency.
