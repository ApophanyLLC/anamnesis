---
title: Parser Adapter Framework
doc_id: DOC-APP-ANAMNESIS-PARSER-ADAPTERS-001
type: reference
status: draft
authority: informative
audience:
- maintainer
scope:
- project
- registry
verification: source-links-reviewed
stability: experimental
owner: athame
last_reviewed: '2026-06-05'
---

# Parser Adapter Framework

Anamnesis core only indexes a stable internal session shape and delegates all
vendor-specific parsing to adapters.

## Internal structured session contract

The core indexer consumes this stable form:

```json
{
  "session_id": "string",
  "source_id": "string",
  "source_type": "string",
  "title": "string",
  "created_at": "ISO-8601 or null",
  "modified_at": "ISO-8601 or null",
  "exchanges": [
    {
      "timestamp": "ISO-8601 or null",
      "role": "user|assistant|...",
      "content": "string"
    }
  ],
  "metadata": {}
}
```

`Exchange` entries are normalized with:
- `role` (`str`)
- `text` (`str`, also surfaced as `content` in the canonical schema)
- `created_at` (`ISO-8601` or `None`)

Core parsing and indexing assumes this contract and should not encode vendor
table names, JSON field names, or transport-specific assumptions directly.

## Parser owner / adapter contract

`SourceDefinition.parser_owner` selects the adapter for a source.

Each adapter module must provide:

- `parse(path: Path, *, source_id: str, source_type: str) -> ParsedSessionFile`
- Optional `fallback_parse(...) -> ParsedSessionFile` for `schema_drift` mode
- `version` (human-readable adapter version string, e.g. `"documents/v1"`)
- Stable registry identity via `owner` (e.g. `"parser_documents"`).

`ParsedSessionFile` fields:

- `documents: tuple[SessionDocument, ...]`
- `parser_mode: "structured" | "raw_text" | "fallback_text"`
- `drift_detected: bool`

If an adapter raises a `SessionParseError` with reason starting with
`"schema_drift:"`, core dispatch falls back to `fallback_parse` when configured.

## External adapter loading

External adapters can be loaded by setting `ANAMNESIS_ADAPTER_MODULES` to a
comma-separated list of importable modules. Each module must expose
`get_adapters() -> tuple[ParserAdapter, ...]`.

```python
from anamnesis.parser_adapters import ParserAdapter


def parse_vendor_file(path: Path, *, source_id: str, source_type: str):
    ...


def get_adapters() -> tuple[ParserAdapter, ...]:
    return (
        ParserAdapter(
            owner="parser_vendor_x",
            version="vendor-x/v1",
            parse=parse_vendor_file,
        ),
    )
```

## Adding a new vendor adapter

1. Add a new adapter implementation in `parser_adapters.py` (or import it from a
   dedicated module).
2. Add a `ParserAdapter` record with:

   - `owner` matching a registry `parser_owner`.
   - `version` aligned with the vendor format/adapter release.
   - `parse` callable.
   - Optional `fallback_parse`.

3. Add/activate the parser owner in source registry definitions only when parser
   behavior and policies are in place.
4. Document migration notes in `CHANGELOG.md` when adapter behavior or supported
   formats changes.

Community adapters should remain in dedicated modules/packages and avoid edits to
core parser modules unless required by a regression.

## Suggested contributor workflow

1. Add/enable a registry definition that points at the new adapter owner.
2. Provide/extend tests for the source’s format transitions.
3. Run the local test suite for parser-adapter-level assertions.
4. Provide upgrade notes for any policy boundary changes in `authorize` prompts.

## Validation expectations

- Active registry `source_type`s should resolve to known adapter owners.
- Unknown adapter owners should not silently enable a source.
- Unknown/unresolved owners must still resolve to the `unassigned` fallback adapter
  for safety, and remain non-authorized by policy until explicitly configured.

## Adapter testing

Community PRs should include parser fixture tests that exercise:

- Known adapter registration for their `parser_owner`.
- Successful `ParsedSessionFile` construction for one vendor sample payload.
- Safe fallback behavior when schema drift is expected.
