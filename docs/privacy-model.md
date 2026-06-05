---
title: Privacy Model
doc_id: DOC-APP-ANAMNESIS-PRIVACY-MODEL-001
type: reference
status: draft
authority: informative
audience:
- user
- maintainer
scope:
- project
- privacy
verification: source-links-reviewed
stability: experimental
owner: athame
last_reviewed: '2026-06-05'
---

# Anamnesis Privacy Model

## What Anamnesis reads

- Source discovery is metadata-only until you authorize a source.
- After authorization, indexing reads only files inside that source’s discovered path.
- Indexing reads sessions/messages and stores normalized session text in local SQLite FTS.
- No browser credentials, editor state, extension configuration, or third-party settings are read.

## What Anamnesis does not read

- Browser plugins, editor extensions, and account credentials.
- System settings, unrelated documents, and files outside discovered source paths.
- Hidden folders in `Downloads`, `Documents`, and other broad home paths unless they are
  explicitly selected as source paths.

## Data storage

- Indexed text is stored in the local `anamnesis.sqlite` database.
- By default, the database is plaintext and written with restrictive file modes.
- If enabled, SQLCipher encrypts the database at rest behind `anamnesis.sqlite`.
- SQLite `secure_delete`, periodic VACUUM, and index rebuilds are used in cleanup and purge
  flows, but not a forensic erase substitute.

## Encryption-at-rest model

- SQLCipher protects the primary index file from direct reads by unauthorized parties
  when the workspace file is stolen.
- Encryption does not protect:
  - plaintext exports and manual input sources before indexing,
  - plaintext tokens held in RAM during search/index operations,
  - copies already written to backups, sync folders, or external snapshots.

## FAQ

### Why is staging required for cloud exports?

Anamnesis does not run cloud credentials or API crawls for privacy reasons.
You decide exactly what gets indexed by staging exported files in the provided import
folders.

### What kinds of files are in scope?

- Manual cloud source folders (for explicit exports): `chatgpt_export`, `claude`,
  `gemini_export`, `character_ai_export`, `notion_export`.
- Local tool-local folders that are pre-vetted by manifest policies.
- No recursive broad-folder scans are performed without explicit authorization.
- The user-selectable encryption mode (`anamnesis encryption --setup`) can reduce
  at-rest exposure of indexed content.

## What the model does not guarantee

- Existing copies in backups, snapshots, cloud sync directories, or filesystem history.
- Instant revocation from external replicas or third-party tools that already saw indexed content.
- Absolute proof of privacy for regulated or highly sensitive workflows.

The design goal is explicit consent and local-readability, not global confidentiality claims.
