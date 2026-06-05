---
title: Anamnesis Web UI (Optional)
doc_id: DOC-APP-ANAMNESIS-WEB-UI-001
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
last_reviewed: '2026-06-04'
code_anchor: []
related_docs: []
supersedes: []
superseded_by: null
machine_summary: Documents the optional local web surface for searching Anamnesis indexes.
human_summary: Adds a browser UI option for running local search without changing the
  core privacy and authorization model.
---

## Scope

This is an optional, local-only convenience layer on top of the existing CLI
search flow. It does not create new index capabilities, sources, or permissions.

## Command

```bash
python -m anamnesis web
```

Flags:

- `--host`: bind address for the local server (default `127.0.0.1`)
- `--port`: bind port (default `8765`)
- `--open`: automatically launch the browser

Examples:

```bash
python -m anamnesis web --open
python -m anamnesis web --host 127.0.0.1 --port 9000
```

## Endpoints

- `GET /` serves a minimal single-page interface with a search box and inline result list.
- `GET /api/search?q=<query>` returns JSON results and index-sync status text.
- `GET /api/health` returns source sync health.
- `GET /api/status` returns `anamnesis status` payload fields.

## Privacy and safety

This UI reads from the same local index used by `anamnesis search`.
It does not read source files directly and does not change discovery,
authorization, indexing, or storage behavior.

For stronger machine-level hardening, enable SQLCipher mode first using
`anamnesis encryption --setup`.
