"""Parsers for file-based Anamnesis session sources."""

from __future__ import annotations

import io
import json
from pathlib import Path
import zipfile

from .models import Exchange, ParsedSessionFile, SessionDocument
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

_JSON_STREAM_CHUNK_BYTES = 65536
_JSON_STREAMING_THRESHOLD_BYTES = 4 * 1024 * 1024


def _streaming_json_payloads(text_stream: io.TextIOBase):
    decoder = json.JSONDecoder()
    buffer = text_stream.read(_JSON_STREAM_CHUNK_BYTES)
    if not buffer:
        return

    # Skip leading whitespace, then route arrays to incremental parsing.
    index = 0
    while index < len(buffer) and buffer[index].isspace():
        index += 1
    if index >= len(buffer):
        return

    if buffer[index] != "[":
        # Single top-level object; keep using standard json for one pass.
        yield json.loads(buffer + text_stream.read())
        return

    # Parse top-level array elements incrementally.
    index += 1
    buffer = buffer[index:]
    while True:
        while True:
            if not buffer:
                buffer = text_stream.read(_JSON_STREAM_CHUNK_BYTES)
                if not buffer:
                    return
            buffer = buffer.lstrip()
            if not buffer:
                continue
            first = buffer[0]
            if first == "]":
                return
            if first == ",":
                buffer = buffer[1:]
                continue
            break

        try:
            value, consumed = decoder.raw_decode(buffer)
        except json.JSONDecodeError:
            chunk = text_stream.read(_JSON_STREAM_CHUNK_BYTES)
            if not chunk:
                raise
            buffer += chunk
            continue
        yield value
        buffer = buffer[consumed:]


def _parse_json_source_documents(
    path: Path,
    *,
    source_id: str,
    source_type: str,
    text_stream: io.TextIOBase | None = None,
    fallback_session_id: str,
) -> tuple:
    stream = text_stream or path.open(encoding="utf-8")
    should_close = text_stream is None
    try:
        payloads = _streaming_json_payloads(stream)
        documents: list[SessionDocument] = []
        for index, payload in enumerate(payloads):
            documents.extend(
                documents_from_payload(
                    payload,
                    source_id=source_id,
                    source_type=source_type,
                    path=path,
                    fallback_session_id=f"{fallback_session_id}:{index}",
                )
            )
        return tuple(documents)
    finally:
        if should_close:
            stream.close()


def parse_zip_export(
    path: Path,
    *,
    source_id: str,
    source_type: str,
) -> ParsedSessionFile:
    documents: list[SessionDocument] = []
    parser_mode = "structured"
    try:
        with zipfile.ZipFile(path) as archive:
            for name in sorted(archive.namelist()):
                if not name.endswith(".json"):
                    continue
                if source_type == "chatgpt_export" and Path(name).name != "conversations.json":
                    continue
                with archive.open(name) as raw_file:
                    with io.TextIOWrapper(
                        raw_file,
                        encoding="utf-8",
                        errors="replace",
                    ) as text_stream:
                        try:
                            fallback_session_id = fallback_session_id_for(
                                path,
                                source_id=source_id,
                                suffix=name,
                            )
                            parsed_documents = _parse_json_source_documents(
                                path,
                                source_id=source_id,
                                source_type=source_type,
                                text_stream=text_stream,
                                fallback_session_id=fallback_session_id,
                            )
                        except json.JSONDecodeError:
                            parsed_documents = ()
                if parsed_documents:
                    documents.extend(parsed_documents)
                    if any(not document.metadata for document in parsed_documents):
                        parser_mode = "raw_text"
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise SessionParseError(path, f"zip_error: {exc}") from exc
    return ParsedSessionFile(tuple(documents), parser_mode=parser_mode)


def parse_json_document(
    path: Path,
    *,
    source_id: str,
    source_type: str,
) -> ParsedSessionFile:
    if path.stat().st_size > _JSON_STREAMING_THRESHOLD_BYTES:
        documents = _parse_json_source_documents(
            path,
            source_id=source_id,
            source_type=source_type,
            fallback_session_id=fallback_session_id_for(path, source_id=source_id),
        )
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
        documents = documents_from_payload(
            payload,
            source_id=source_id,
            source_type=source_type,
            path=path,
            fallback_session_id=fallback_session_id_for(path, source_id=source_id),
        )
    if documents:
        parser_mode = "structured"
        if any(not document.metadata for document in documents):
            parser_mode = "raw_text"
        return ParsedSessionFile(tuple(documents), parser_mode=parser_mode)
    return ParsedSessionFile(
        (fallback_document(path, source_id=source_id, source_type=source_type),),
        parser_mode="raw_text",
    )


def parse_jsonl_document(
    path: Path,
    *,
    source_id: str,
    source_type: str,
) -> ParsedSessionFile:
    exchanges: list[Exchange] = []
    with path.open(encoding="utf-8") as handle:
        lines = handle
        for line in lines:
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
                        role=str(
                            payload.get("role") or payload.get("author") or "unknown"
                        ),
                        text=text,
                        created_at=coerce_datetime_text(payload),
                    )
                )
    return ParsedSessionFile(
        (
            build_document(
                path,
                source_id=source_id,
                source_type=source_type,
                session_id=fallback_session_id_for(path, source_id=source_id),
                title=path.stem,
                created_at=None,
                exchanges=tuple(exchanges),
                metadata={},
            ),
        ),
        parser_mode="raw_text",
    )


def parse_text_document(
    path: Path,
    *,
    source_id: str,
    source_type: str,
) -> ParsedSessionFile:
    return ParsedSessionFile(
        (
            build_document(
                path,
                source_id=source_id,
                source_type=source_type,
                session_id=fallback_session_id_for(path, source_id=source_id),
                title=path.stem,
                created_at=None,
                exchanges=text_document_exchanges(path.read_text(encoding="utf-8")),
                metadata={},
            ),
        ),
        parser_mode="raw_text",
    )
