"""Parser dispatch facade for Anamnesis session files."""

from __future__ import annotations

from pathlib import Path

from .models import SessionDocument
from .parser_common import SessionParseError
from .parser_copilot import COPILOT_SQLITE_SUFFIXES, parse_copilot_sqlite
from .parser_documents import (
    parse_json_document,
    parse_jsonl_document,
    parse_text_document,
    parse_zip_export,
)


def parse_session_file(
    path: Path,
    *,
    source_id: str,
    source_type: str,
) -> tuple[SessionDocument, ...]:
    suffix = path.suffix.lower()
    if source_type == "copilot_vscode" and suffix in COPILOT_SQLITE_SUFFIXES:
        return parse_copilot_sqlite(
            path,
            source_id=source_id,
            source_type=source_type,
        )
    if suffix == ".zip":
        return parse_zip_export(path, source_id=source_id, source_type=source_type)
    if suffix == ".json":
        if source_type == "chatgpt_export" and path.name != "conversations.json":
            return ()
        return parse_json_document(path, source_id=source_id, source_type=source_type)
    if suffix == ".jsonl":
        return (
            parse_jsonl_document(path, source_id=source_id, source_type=source_type),
        )
    return (parse_text_document(path, source_id=source_id, source_type=source_type),)


__all__ = ["SessionParseError", "parse_session_file"]
