"""Parser dispatch facade for Anamnesis session files."""

from __future__ import annotations

from pathlib import Path

from .models import ParsedSessionFile
from .parser_common import SessionParseError
from .parser_adapters import get_adapter


def parse_session_file(
    path: Path,
    *,
    source_id: str,
    source_type: str,
    parser_owner: str | None = None,
) -> ParsedSessionFile:
    if parser_owner is None:
        parser_owner = "unassigned"

    adapter = get_adapter(parser_owner)
    try:
        return adapter.parse(
            path,
            source_id=source_id,
            source_type=source_type,
        )
    except SessionParseError as exc:
        if not str(exc.reason).startswith("schema_drift:"):
            raise
        if adapter.fallback_parse is None:
            raise
        fallback = adapter.fallback_parse(
            path,
            source_id=source_id,
            source_type=source_type,
        )
        return ParsedSessionFile(
            fallback.documents,
            parser_mode="raw_text",
            drift_detected=True,
        )


__all__ = ["SessionParseError", "parse_session_file"]
