---
title: Anamnesis Product Brief
doc_id: DOC-APP-ANAMNESIS-PRODUCT-BRIEF-001
type: brief
status: draft
authority: informative
audience:
- maintainer
- contributor
scope:
- project
- product
verification: manually-reviewed
stability: experimental
owner: athame
last_reviewed: '2026-06-03'
source_note: Derived from a stale Apophany Anamnesis proposal and updated to
  match the current repository behavior.
---

# Anamnesis Product Brief

## Purpose

Capture the current product narrative for Anamnesis without overstating the
capabilities in this source snapshot.

## One-line Positioning

Anamnesis is a local-first session archaeology tool for finding useful AI work
history that is otherwise scattered across assistant apps, export files, and
local session stores.

## Problem

AI-assisted work creates a new kind of memory loss. Developers and knowledge
workers regularly make architectural decisions, debug problems, synthesize
domain knowledge, and explore alternatives inside AI sessions. Those sessions
often become hard to recover once the tool moves on to the next prompt.

The problem is structural:

- Most assistant products optimize for forward motion, not retrospective search.
- Cross-tool search is absent.
- Session formats differ across JSON, JSONL, Markdown, text, SQLite, ZIP
  exports, and workspace artifacts.
- Cloud products expose account exports or privacy dashboards, while local tools
  may store transcripts directly on disk.
- Users often remember the idea but not the tool, date, title, or exact words.

Anamnesis exists to make that past work discoverable again while respecting the
sensitivity of the underlying data.

## Current Product Shape

The current snapshot is an initial local MVP. It provides:

- Inventory-only discovery for governed source definitions.
- Explicit authorization before reading source content.
- Local parsing for JSON, JSONL, Markdown, text, ZIP JSON members, and
  conservative VS Code Copilot/chat-shaped SQLite records.
- Local SQLite FTS5 indexing and CLI lexical search.
- Revocation that purges source chunks, rebuilds FTS data, and vacuums the
  local database.
- A privacy audit for workspace, database, authorization manifest, SQLite
  sidecar modes, and SQLite `secure_delete` status.
- A governed source registry with policy snapshot identifiers so authorization
  binds to the source policy that was discovered.

This snapshot does not yet provide vector search, local embeddings, synthesis,
a web UI, an IDE extension, or team knowledge bases. Those remain roadmap
concepts.

## Privacy Model

Anamnesis treats AI session history as highly sensitive local data. Session
archives can contain business logic, private reasoning, half-formed ideas,
personal context, credentials accidentally pasted into prompts, and unpublished
work product.

The core permission model has three stages:

1. Discover: report source path, file count, size, and date range without
   reading session content.
2. Authorize: persist an explicit user authorization record for selected
   sources.
3. Index and query: parse and index only authorized sources into a local SQLite
   database.

Core commitments for this repo:

- Do not ask for AI account credentials.
- Do not read session content during discovery.
- Do not scan broad home-directory locations for cloud assistant exports.
- Do not make cloud sync a hidden requirement for core indexing/search.
- Allow revocation to purge indexed chunks for a source.
- Keep the workspace, authorization manifest, database, and SQLite sidecars
  permission-restricted.

This is not a forensic-erasure guarantee. Filesystem snapshots, backups, disk
wear-leveling, external sync tools, or copied database files can retain data
outside Anamnesis control. Encryption-at-rest remains a stronger future design
direction for highly sensitive archives.

## Source Policy

Source support is governed by the registry and by
`docs/source-access-matrix.md`.

Active discovery should remain narrow:

- Auto-discover only product-owned local paths with explicit file eligibility
  rules and tests.
- Treat cloud account-history products as explicit import roots under
  `~/Anamnesis`.
- Prefer product exports for workspace tools and products whose raw local
  storage is not a stable public contract.
- Treat runtimes such as Ollama as client-dependent rather than direct
  conversation-history sources.
- Keep underdocumented products in backlog until a stable path/export shape,
  parser, and safety tests exist.

Current active examples include Codex session files and conservative VS Code
Copilot/chat workspace SQLite scanning. ChatGPT, Claude web/Desktop, Gemini
Apps, Character.AI, Notion, and other cloud/workspace sources should enter
through explicit user-supplied exports.

## Architecture Direction

The implementation should stay modular:

- Discovery inventories candidate source roots and file metadata.
- Authorization records user consent and the source policy snapshot.
- Parsers normalize source files into session documents and exchanges.
- Indexing stores source metadata, sessions, chunks, and FTS data locally.
- Search queries the local index and returns source/session/path context.

Future vector search should fit into this shape rather than replacing the
permission boundary. Local embeddings should be optional and should preserve the
same source authorization and revocation semantics.

## Roadmap Themes

Near-term hardening:

- Streaming parsers for large JSON and ZIP exports.
- More source-specific tests for cloud export layouts and local tool formats.
- Better diagnostics for skipped files, parse failures, and source policy drift.
- Legacy authorization migration for manifests created before policy snapshots.

Search and retrieval:

- Local embeddings and vector search.
- Hybrid lexical plus semantic ranking.
- Project or workspace filters that do not require reading unauthorized content.
- Export of selected search results or summaries to Markdown.

Source ecosystem:

- Claude Code and Gemini CLI local import candidates after current path and
  format verification.
- Export adapters for Open WebUI, AnythingLLM, LM Studio, Jan, and VS Code chat
  JSON exports.
- Workspace artifact handling for Notion, Lindy, and similar products.
- Parser registry conventions once source-specific adapters become numerous.

Interfaces:

- CLI remains the durable operator surface.
- A local web UI may support browsing, triage, and search result review.
- IDE integration can surface relevant prior session context near current work,
  but should not weaken local-first privacy assumptions.

## Risks

Parser drift:

Upstream tools can change local formats or export layouts without notice.
Mitigation: source-specific tests, clear drift warnings, graceful skipped-file
diagnostics, and policy snapshot checks.

Overbroad discovery:

Broad filesystem scans can surprise users and index unrelated sensitive data.
Mitigation: narrow default paths, manual import roots, explicit authorization,
and registry governance.

False confidence in purge:

SQLite and filesystem behavior can leave data in sidecars, backups, or copied
files. Mitigation: FTS rebuild, `secure_delete`, `VACUUM`, restrictive file
modes, privacy audit, and honest documentation.

Compute cost:

Future local embedding or synthesis features may be slow on older machines.
Mitigation: incremental indexing, resumable jobs, progress reporting, and
lexical search fallback.

Relevance quality:

Search is useful only when results are scoped and understandable. Mitigation:
source metadata, paths, timestamps, project filters, transparent diagnostics,
and user-controlled inclusion.

## Product Principle

The product promise is not that Anamnesis knows every assistant format forever.
The promise is that it treats the user's past AI work as their own local
archive, asks before reading it, indexes only what was authorized, and makes
the recoverable parts searchable without turning private history into another
cloud dependency.
