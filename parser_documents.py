"""Parsers for file-based Anamnesis session sources."""

from __future__ import annotations

import json
from pathlib import Path
import zipfile

from .models import Exchange, SessionDocument
from .parser_common import (
    build_document,
    coerce_datetime_text,
    documents_from_payload,
    fallback_document,
    fallback_session_id_for,
    SessionParseError,
    text_document_exchanges,
    text_from_node,
)


def parse_zip_export(
    path: Path,
    *,
    source_id: str,
    source_type: str,
) -> tuple[SessionDocument, ...]:
    documents: list[SessionDocument] = []
    try:
        with zipfile.ZipFile(path) as archive:
            for name in sorted(archive.namelist()):
                if not name.endswith(".json"):
                    continue
                if source_type == "chatgpt_export" and Path(name).name != "conversations.json":
                    continue
                raw = archive.read(name).decode("utf-8")
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                documents.extend(
                    documents_from_payload(
                        payload,
                        source_id=source_id,
                        source_type=source_type,
                        path=path,
                        fallback_session_id=fallback_session_id_for(
                            path,
                            source_id=source_id,
                            suffix=name,
                        ),
                    )
                )
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise SessionParseError(path, f"zip_error: {exc}") from exc
    return tuple(documents)


def parse_json_document(
    path: Path,
    *,
    source_id: str,
    source_type: str,
) -> tuple[SessionDocument, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    documents = documents_from_payload(
        payload,
        source_id=source_id,
        source_type=source_type,
        path=path,
        fallback_session_id=fallback_session_id_for(path, source_id=source_id),
    )
    if documents:
        return documents
    return (fallback_document(path, source_id=source_id, source_type=source_type),)


def parse_jsonl_document(
    path: Path,
    *,
    source_id: str,
    source_type: str,
) -> SessionDocument:
    exchanges: list[Exchange] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            exchanges.append(Exchange(role="unknown", text=line))
            continue
        text = text_from_node(payload)
        if text:
            exchanges.append(
                Exchange(
                    role=str(payload.get("role") or payload.get("author") or "unknown"),
                    text=text,
                    created_at=coerce_datetime_text(payload),
                )
            )
    return build_document(
        path,
        source_id=source_id,
        source_type=source_type,
        session_id=fallback_session_id_for(path, source_id=source_id),
        title=path.stem,
        created_at=None,
        exchanges=tuple(exchanges),
        metadata={},
    )


def parse_text_document(
    path: Path,
    *,
    source_id: str,
    source_type: str,
) -> SessionDocument:
    return build_document(
        path,
        source_id=source_id,
        source_type=source_type,
        session_id=fallback_session_id_for(path, source_id=source_id),
        title=path.stem,
        created_at=None,
        exchanges=text_document_exchanges(path.read_text(encoding="utf-8")),
        metadata={},
    )
