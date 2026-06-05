---
title: Manual Export Source Onboarding
doc_id: DOC-APP-ANAMNESIS-MANUAL-EXPORT-GUIDANCE-001
type: reference
status: draft
authority: informative
audience:
- user
- maintainer
scope:
- project
- onboarding
verification: source-links-reviewed
stability: experimental
owner: athame
last_reviewed: '2026-06-05'
---

# Manual Export Source Onboarding

Anamnesis keeps cloud products explicit and manual-only by design.
You must provide exports before authorization and indexing.

For each manual source, Anamnesis discovery shows the exact import path and
basic steps:

1. Export data from the vendor UI.
2. Copy the export into the displayed import path.
3. Run `python -m anamnesis authorize <source_id>`.
4. Run `python -m anamnesis index`.

This design preserves a local-first privacy boundary:

- No cloud credentials are needed by Anamnesis.
- No API scanning happens automatically.
- Discovery stays metadata-only until you authorize a source.

## Manual import paths and hints

- `chatgpt_export` → `~/Anamnesis/chatgpt_exports`
- `claude` → `~/Anamnesis/imports/claude`
- `gemini_export` → `~/Anamnesis/imports/gemini`
- `character_ai_export` → `~/Anamnesis/imports/character_ai`
- `notion_export` → `~/Anamnesis/imports/notion`

`discover` prints these paths in `manual_import_paths` and includes source-specific
instructions for how to populate them.

## Current limitation and future work

Some vendors do not expose reliable local indexing hooks, so this is
manual-first for the MVP.

Medium-term work includes:

- Vendor export launch helpers.
- Browser-based workflow assistance for supported sites.
- Desktop integrations where vendors provide safe local export APIs.
