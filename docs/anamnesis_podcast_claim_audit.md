---
title: Anamnesis Podcast Claim Audit
type: audit
status: draft
authority: informative
audience:
- maintainer
- producer
scope:
- project
- podcast-script
verification: repo-evidence-reviewed
stability: experimental
---

# Anamnesis Podcast Claim Audit

This audit grounds the revised audio script in repository evidence. Claims that
could not be supported from the repository were removed or reframed as open
roadmap questions.

## Evidence Map

| Script claim | Repository evidence |
|---|---|
| Anamnesis is a local-first session archaeology app for AI session history. | `README.md` lines 47-54; `docs/product-brief.md` lines 31-49. |
| The current status is an initial, experimental MVP for developers and maintainers, not a hardened archival security product. | `README.md` lines 47-60; `README.md` lines 62-69; `docs/product-brief.md` lines 74-79. |
| Discovery, authorization, indexing, search, privacy audit, and revoke are current CLI surfaces. | `README.md` lines 100-125; `cli.py` command definitions. |
| Discovery inventories known sources without reading session content. | `README.md` lines 51-54 and 136-139; `discovery.py` lines 21-75. |
| Discovery reports path, file count, total bytes, and first/last modified timestamps. | `README.md` lines 136-139; `discovery.py` lines 45-71. |
| Discovery is governed by registry definitions rather than broad home-directory scanning. | `README.md` lines 164-180; `registry.py` lines 62-201. |
| Candidate files are recursively enumerated inside configured source roots, so the accurate claim is "no broad crawl," not "no recursion." | `discovery.py` lines 87-111. |
| Codex and VS Code Copilot workspace storage are active product-owned local discovery examples. | `README.md` lines 71-85; `docs/source-access-matrix.md` lines 44-56. |
| Cloud/account-history products enter through explicit import roots under `~/Anamnesis`. | `README.md` lines 75-83 and 164-171; `registry.py` lines 63-163. |
| ChatGPT discovery accepts only ZIPs containing `conversations.json` or extracted `conversations.json`. | `README.md` lines 80-83; `discovery.py` lines 114-134; tests in `tests/test_anamnesis_mvp.py` around ChatGPT export behavior. |
| Authorizations are stored in `sources.authorization.json` with a `definition_id`. | `README.md` lines 78-88; `authorization.py` lines 20-31 and 75-92. |
| The policy snapshot identifier is a hash over source-definition fields. | `models.py` lines 116-137. |
| Indexing detects unknown/stale policy identifiers and returns `source_policy_drift` diagnostics for that source. | `service.py` lines 57-75 and 149-152; `tests/test_archive_safety.py` policy drift tests. |
| The current manifest stores the hash, not the full serialized old policy, so current CLI cannot render an old-versus-new policy diff. | `models.py` lines 66-75; `authorization.py` lines 20-31 and 77-87. |
| Current CLI output is JSON and does not include an interactive reauthorization prompt or policy diff. | `cli.py` command handlers; `README.md` CLI examples lines 100-125. |
| Indexing parses only authorized sources and records skipped-file diagnostics for parse failures. | `service.py` lines 50-152. |
| Revoking a source purges chunks, rebuilds FTS, and vacuums the database. | `README.md` lines 136-143; `index.py` purge behavior. |
| The local database is plaintext SQLite using SQLite FTS5. | `README.md` lines 62-69 and 195-196; `index.py` lines 19-47. |
| File and directory permissions are restricted to `700` for workspace directories and `600` for database/authorization files. | `README.md` lines 145-153; `filesystem.py` lines 9-18; `service.py` privacy audit lines 157-237. |
| `privacy-audit` checks permissions, SQLite sidecars, and `secure_delete`, and warns that this is not encryption-at-rest. | `README.md` lines 150-158; `service.py` lines 157-237. |
| VS Code Copilot parsing is conservative and depends on known SQLite table shapes plus chat/Copilot markers. | `README.md` lines 198-204; `parser_copilot.py` lines 16-23, 70-130, and 155-216. |
| Unrecognized VS Code tables or rows are skipped rather than guessed. | `parser_copilot.py` lines 65-72, 93-94, and 155-193. |
| Malformed SQLite files are reported as skipped diagnostics. | `parser_copilot.py` lines 26-54; `service.py` lines 104-112; `tests/test_anamnesis_mvp.py` malformed SQLite test. |
| JSON, JSONL, Markdown, text, ZIP JSON members, mapping traversal, and bounded text chunking are implemented. | `README.md` lines 80-97; `parser_documents.py`; `parser_common.py` lines 12-13 and 252-289. |
| Large JSON and ZIP members are still loaded as whole members, and streaming parsers are future hardening. | `README.md` lines 206-208; `docs/product-brief.md` lines 152-159. |
| Better diagnostics for skipped files, parse failures, and source policy drift are a near-term roadmap theme. | `docs/product-brief.md` lines 152-159. |
| Vector search, embeddings, web UI, IDE extension, and team knowledge bases are not current MVP features. | `docs/product-brief.md` lines 57-72; `README.md` lines 195-196. |

## Draft Claims Removed Or Reframed

- Removed the claim that the project is already publicly hosted on GitHub. The
  README says public installation support is experimental and the package is
  intended for private Apophany source consumption during the current cutover.
- Removed claims about implemented `--yes`, `--auto-approve`, `--no-warnings`,
  `status`, search-scope manifests, persistent staleness banners, and interactive
  drift diffing. The repo supports these only as roadmap-adjacent ideas, not
  current behavior.
- Reframed "no recursive crawler" to "no broad home-directory crawl." The code
  does use `rglob` recursively inside configured source roots.
- Removed claims of zero telemetry, daemon behavior, and personal dogfooding
  anecdotes unless framed as non-evidenced discussion. The repo does not provide
  direct evidence for those specifics.
- Reframed broad psychological claims as the developer's design rationale rather
  than factual assertions about all users.
