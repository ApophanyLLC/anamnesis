"""Vendor-adapter registry for session parsers.

Adapters are the only components that know how to interpret vendor formats.
Core parsing stays format-neutral by asking adapters to provide extracted session
documents and treating any adapter failure as structured-to-text fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .models import ParsedSessionFile
from .parser_copilot import COPILOT_SQLITE_SUFFIXES, parse_copilot_sqlite
from .parser_documents import (
    parse_json_document,
    parse_jsonl_document,
    parse_text_document,
    parse_zip_export,
)

ParseFn = Callable[..., ParsedSessionFile]


@dataclass(frozen=True)
class ParserAdapter:
    """Metadata and entrypoints for one parser owner family."""

    owner: str
    version: str
    parse: ParseFn
    fallback_parse: ParseFn | None = None


def parse_documents_adapter(
    path: Path,
    *,
    source_id: str,
    source_type: str,
) -> ParsedSessionFile:
    """Parse common file-based document exports.

    This adapter intentionally stays thin and delegates to the structured parser
    implementations for zip/json/jsonl/text payloads.
    """

    suffix = path.suffix.lower()
    if suffix == ".zip":
        return parse_zip_export(path, source_id=source_id, source_type=source_type)
    if suffix == ".json":
        if source_type == "chatgpt_export" and path.name != "conversations.json":
            return ParsedSessionFile(
                tuple(),
                parser_mode="raw_text",
            )
        return parse_json_document(path, source_id=source_id, source_type=source_type)
    if suffix == ".jsonl":
        return parse_jsonl_document(path, source_id=source_id, source_type=source_type)
    return parse_text_document(path, source_id=source_id, source_type=source_type)


def parse_copilot_adapter(
    path: Path,
    *,
    source_id: str,
    source_type: str,
) -> ParsedSessionFile:
    if path.suffix.lower() not in COPILOT_SQLITE_SUFFIXES:
        return parse_text_document(path, source_id=source_id, source_type=source_type)
    return parse_copilot_sqlite(
        path,
        source_id=source_id,
        source_type=source_type,
    )


_KNOWN_ADAPTERS: tuple[ParserAdapter, ...] = (
    ParserAdapter(
        owner="parser_documents",
        version="documents/v1",
        parse=parse_documents_adapter,
        fallback_parse=parse_text_document,
    ),
    ParserAdapter(
        owner="parser_documents_candidate",
        version="documents/v1-candidate",
        parse=parse_documents_adapter,
        fallback_parse=parse_text_document,
    ),
    ParserAdapter(
        owner="parser_copilot",
        version="copilot-sqlite/v1",
        parse=parse_copilot_adapter,
        fallback_parse=parse_text_document,
    ),
    ParserAdapter(
        owner="parser_copilot_candidate",
        version="copilot-sqlite/v1-candidate",
        parse=parse_copilot_adapter,
        fallback_parse=parse_text_document,
    ),
    ParserAdapter(
        owner="unassigned",
        version="unassigned",
        parse=parse_text_document,
    ),
)


def adapters() -> tuple[ParserAdapter, ...]:
    """Return the registered parser adapters."""

    return _KNOWN_ADAPTERS


def adapter_owner(owner: str) -> ParserAdapter:
    """Resolve a parser owner id with a safe fallback."""

    return get_adapter(owner)


def _build_adapter_index() -> dict[str, ParserAdapter]:
    registry: dict[str, ParserAdapter] = {}
    for adapter in _KNOWN_ADAPTERS:
        registry[adapter.owner] = adapter
    return registry


_ADAPTERS = _build_adapter_index()


def get_adapter(parser_owner: str) -> ParserAdapter:
    """Resolve an adapter for a parser owner with a safe fallback."""

    return _ADAPTERS.get(parser_owner) or _ADAPTERS["unassigned"]


__all__ = [
    "ParseFn",
    "ParserAdapter",
    "adapters",
    "adapter_owner",
    "get_adapter",
    "parse_copilot_adapter",
    "parse_documents_adapter",
]
