---
title: Anamnesis
doc_id: DOC-APP-ANAMNESIS-README-001
type: guide
status: implemented
authority: informative
audience:
- user
- maintainer
scope:
- project
- repo-tools
verification: manually-reviewed
stability: experimental
owner: athame
reviewers:
- maintainer
last_reviewed: '2026-06-01'
code_anchor: []
related_docs: []
supersedes: []
superseded_by: null
machine_summary: Introduces the governed README for the local-first Anamnesis session
  archaeology app.
human_summary: Anamnesis is a local-first session archaeology and search app with explicit
  authorization and local indexing.
---

## Purpose
Introduce the Anamnesis app surface and operational constraints.

## What this page is
The public-facing overview for Anamnesis local app usage and behavior.

## What this page is not
An implementation guide for authorization internals or security architecture.

## Current status
implemented

## Authority level
informative

## Evidence basis
manually reviewed documentation.

Status: initial MVP
Audience: developers and maintainers
Purpose: local-first discovery, authorization, indexing, and search for AI session history

Anamnesis is a local-first session archaeology app. It inventories known AI
session stores without reading content, records explicit user authorization for
each source, indexes authorized sessions into a local SQLite database, and
offers CLI search over the resulting index.

## Current MVP

- Discovers known product-owned local stores for Codex and VS Code
  Copilot/chat workspace storage.
- Treats cloud/account-history products such as ChatGPT, Claude, Gemini,
  Character.AI, and Notion as manual import surfaces that must enter through
  explicit export files under `~/Anamnesis`.
- Separates discovery from content reads.
- Persists explicit authorization in `sources.authorization.json`.
- Parses JSON, JSONL, Markdown, and text source files; ZIP export parsing reads
  JSON members only.
- Limits ChatGPT export discovery to `~/Anamnesis/chatgpt_exports`, accepting
  only OpenAI export ZIPs or extracted `conversations.json` files.
- Limits VS Code workspace storage parsing to `.db`, `.sqlite`, and `.vscdb`
  records with explicit chat/Copilot table or key markers.
- Uses a governed source capability registry for source type, access mode,
  default discovery policy, accepted file shapes, risk level, parser owner,
  and a policy snapshot identifier for each definition.
- Maintains source-access guidance in
  `docs/source-access-matrix.md`, including export-first, cloud-export-only,
  runtime-only, and docs-backlog source categories.
- Traverses ChatGPT-style mapping exports by parent/child links when present.
- Splits long text and Markdown source files into bounded chunks before FTS
  indexing.
- Indexes normalized session exchanges into SQLite FTS5.
- Searches indexed history with a local CLI.

## CLI

This checkout is a non-installable source snapshot: there is no
`pyproject.toml` in the tree, so it is not packaged as a wheel or sdist.
Work from the checkout's parent directory, or add that parent to
`PYTHONPATH`, and use the module entrypoint directly:

```bash
python -m anamnesis discover
python -m anamnesis authorize "<source_id>"
python -m anamnesis index
python -m anamnesis privacy-audit
python -m anamnesis privacy-audit --fix-permissions
python -m anamnesis search "auth architecture decision"
python -m anamnesis revoke "<source_id>"
```

For a standalone exported snapshot that contains a top-level `anamnesis/`
package, run commands from the snapshot root with that root on `PYTHONPATH`:

```bash
PYTHONPATH=. python -m anamnesis discover
```

Use `--workspace <path>` to choose a different Anamnesis data directory. The
default is `~/.anamnesis`.

Use `--home <path>` to point discovery at a test or alternate home directory.

## Tests

In this repository, Anamnesis carries package-local safety tests so maintainers
can verify the privacy boundary without the full repository test tree:

```bash
python -m pytest tests
```

For a standalone exported snapshot whose tests are shipped under
`anamnesis/tests`, use the snapshot layout instead:

```bash
PYTHONPATH=. python -m pytest anamnesis/tests
```

From the full repository, the broader app regression suite is:

```bash
python -m pytest tests
```

## Privacy Boundary

Discovery reports file counts, size, date range, and path only. Session content
is read only after a source is explicitly authorized. Revoking a source purges
its indexed chunks from the local database. Anamnesis enables SQLite
`secure_delete` on index connections, rebuilds the FTS index after source
purge, and then runs `VACUUM` so ordinary revoked index text is compacted out
of `anamnesis.sqlite`.

Anamnesis creates its workspace directory with `700` permissions and its local
database and authorization manifest with `600` permissions:
`~/.anamnesis/anamnesis.sqlite` and
`~/.anamnesis/sources.authorization.json`.

Use `anamnesis privacy-audit` to inspect local file modes, SQLite sidecar file
modes, and SQLite `secure_delete` status without reading indexed content. Use
`anamnesis privacy-audit --fix-permissions` to repair only known Anamnesis
workspace, database, authorization, and SQLite sidecar file modes.

This is not a guarantee of forensic erasure from filesystem snapshots, backups,
disk wear-leveling, external sync tools, or already-copied database files.
Encryption-at-rest remains the stronger design direction for highly sensitive
archives.

Cloud assistant exports are not discovered from broad home-directory locations
such as `~/Downloads` or hidden app-history folders. Place explicit exports in
their Anamnesis import roots before authorizing them, for example an OpenAI ZIP
or extracted `conversations.json` in `~/Anamnesis/chatgpt_exports`, Claude
exports in `~/Anamnesis/imports/claude`, Gemini exports in
`~/Anamnesis/imports/gemini`, Character.AI exports in
`~/Anamnesis/imports/character_ai`, and Notion exports in
`~/Anamnesis/imports/notion`.

Source capabilities are declared in `registry.py`. A source must
have an explicit access mode, default discovery policy, accepted file shapes,
risk level, confidence level, parser owner, storage model, local path/format,
user access steps, drift warning, and a policy snapshot identifier before
discovery or indexing should rely on it. Use `auto_discover_local` only for
narrow, product-owned local storage paths. Use `manual_import_only` for cloud
exports and broad user-supplied content so authorization never implies scanning
unrelated files.

The registry also carries a non-active backlog for local, export, and
direct-file candidates identified from the source access matrix: Gemini
Antigravity, LM Studio, Jan, Open WebUI, Codex CLI history, GitHub Copilot CLI,
and GitHub Copilot in VS Code follow-ups. These records are governance seeds
only. They are not part of default discovery until a source-specific parser,
file eligibility rule, and safety test promote them into
`SOURCE_CAPABILITY_REGISTRY`.

Low-confidence products such as xAI Grok, Sai by Simular, Qwen, and consumer
Poe are docs/backlog-only. They have no default discovery suffixes and should
not become importable until a primary-source export path or local session path
has been verified and covered by source-specific safety tests.

The current MVP uses lexical SQLite FTS search. Local embeddings and vector
storage are the next implementation layer.

## Parser Limits

The VS Code Copilot/chat parser still depends on known SQLite table shapes plus
chat/Copilot markers in table names, keys, or IDs. That is intentionally
conservative compared with broad extension-state indexing, but VS Code storage
schemas can drift and may still need source-specific adapters for better recall
and fewer false positives.

Large JSON and ZIP members are still loaded as whole members before
normalization. Very large ChatGPT exports should move to a streaming parser
before this surface is treated as a high-volume archival importer.
