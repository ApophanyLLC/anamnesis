"""Parsers for VS Code Copilot/chat workspace storage."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sqlite3

from .models import Exchange, ParsedSessionFile, SessionDocument
from .parser_common import SessionParseError, build_document, documents_from_payload


COPILOT_SQLITE_SUFFIXES = (".db", ".sqlite", ".sqlite-journal", ".vscdb")

_COPILOT_TABLE_SIGNATURES = (
    (("id", "key", "value"), ("id", "row_id"), ("value",), "copilot"),
    (("key", "value"), ("row_id",), ("value",), "copilot"),
    (("sessionid", "messages"), ("sessionid",), ("messages",), "session"),
    (("session_id", "messages_payload"), ("session_id",), ("messages_payload",), "session"),
)

_COPILOT_CHAT_MARKER = re.compile(r"(?i)(?:^|[^a-z0-9])(copilot|chat)(?:$|[^a-z0-9])")


def parse_copilot_sqlite(
    path: Path,
    *,
    source_id: str,
    source_type: str,
) -> ParsedSessionFile:
    documents: list[SessionDocument] = []
    table_names: list[str] = []
    try:
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        with connection:
            table_rows = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
            table_names = [row["name"] for row in table_rows]
            matched_signature = False

            for table_name in table_names:
                table_info = connection.execute(
                    f"PRAGMA table_info({_quote_identifier(table_name)})"
                ).fetchall()
                columns = [column[1] for column in table_info]
                if _match_copilot_signature(columns) is not None:
                    matched_signature = True
                documents.extend(
                    _parse_copilot_table(
                        connection,
                        table_name=table_name,
                        source_id=source_id,
                        source_type=source_type,
                        path=path,
                    )
                )
            if table_names and not matched_signature:
                raise SessionParseError(
                    path,
                    "schema_drift: no recognized copilot/session table shape found",
                )
    except sqlite3.Error as exc:
        raise SessionParseError(path, f"sqlite_error: {exc}") from exc
    return ParsedSessionFile(tuple(documents), parser_mode="structured")


def _parse_copilot_table(
    connection: sqlite3.Connection,
    *,
    table_name: str,
    source_id: str,
    source_type: str,
    path: Path,
) -> tuple[SessionDocument, ...]:
    table_info = connection.execute(f"PRAGMA table_info({_quote_identifier(table_name)})").fetchall()
    columns = [column[1] for column in table_info]
    if not columns:
        return ()

    signature = _match_copilot_signature(columns)
    if signature is None:
        return ()

    id_column, payload_columns, title_fallback = signature
    query_column_names = ["rowid"]
    id_column_index = 0
    if id_column:
        query_column_names.append(id_column)
        id_column_index = 1
    for marker_column in columns:
        if marker_column.lower() not in ("key", "id", "session_id", "sessionid"):
            continue
        if marker_column not in query_column_names:
            query_column_names.append(marker_column)
    payload_column_indexes: list[int] = []
    for payload_column in payload_columns:
        if payload_column not in query_column_names:
            query_column_names.append(payload_column)
        if payload_column not in columns:
            continue
        payload_column_indexes.append(query_column_names.index(payload_column))

    if not payload_column_indexes:
        return ()

    quoted_columns = ", ".join(_quote_identifier(column) for column in query_column_names)
    rows = connection.execute(
        f"SELECT {quoted_columns} FROM {_quote_identifier(table_name)} ORDER BY rowid"
    ).fetchall()
    return _documents_from_columns(
        rows,
        source_id=source_id,
        source_type=source_type,
        path=path,
        table_name=table_name,
        id_column_index=id_column_index,
        payload_columns=tuple(payload_column_indexes),
        title_fallback=title_fallback,
    )


def _match_copilot_signature(columns: list[str]) -> tuple[str | None, tuple[str, ...], str] | None:
    normalized = {column.lower(): column for column in columns}
    for required_columns, id_columns, payload_columns, title_fallback in _COPILOT_TABLE_SIGNATURES:
        if not all(required in normalized for required in required_columns):
            continue
        selected_payload_columns = tuple(
            normalized[name]
            for name in payload_columns
            if name in normalized
        )
        if not selected_payload_columns:
            continue
        selected_id_column = None
        for candidate in id_columns:
            if candidate in normalized:
                selected_id_column = normalized[candidate]
                break
        return selected_id_column, selected_payload_columns, title_fallback
    return None


def _documents_from_columns(
    rows: tuple[sqlite3.Row, ...],
    *,
    source_id: str,
    source_type: str,
    path: Path,
    table_name: str,
    id_column_index: int,
    payload_columns: tuple[int, ...],
    title_fallback: str = "copilot",
) -> tuple[SessionDocument, ...]:
    documents: list[SessionDocument] = []
    for row in rows:
        row_id = str(row[id_column_index] or "unresolved")
        title = f"{title_fallback}:{table_name}:{row_id}"
        payload_found = False
        for payload_column in payload_columns:
            if payload_column >= len(row):
                continue
            raw = row[payload_column]
            if raw is None:
                continue
            if not _row_is_copilot_chat_scoped(
                row,
                table_name=table_name,
                id_column_index=id_column_index,
                payload_column=payload_column,
            ):
                continue
            parsed = _try_load_json(raw)
            if parsed is not None:
                documents.extend(
                    documents_from_payload(
                        parsed,
                        source_id=source_id,
                        source_type=source_type,
                        path=path,
                        fallback_session_id=f"{source_id}:{table_name}:{row_id}:{payload_column}",
                    )
                )
                payload_found = True
                continue

            text = str(raw).strip()
            if text:
                docs = build_document(
                    path=path,
                    source_id=source_id,
                    source_type=source_type,
                    session_id=f"{source_id}:{table_name}:{row_id}:{payload_column}",
                    title=title,
                    created_at=None,
                    exchanges=(Exchange(role="copilot", text=text),),
                    metadata={"table": table_name, "row_id": row_id},
                )
                documents.append(docs)
                payload_found = True

        if not payload_found:
            continue
    return tuple(documents)


def _row_is_copilot_chat_scoped(
    row: sqlite3.Row,
    *,
    table_name: str,
    id_column_index: int,
    payload_column: int,
) -> bool:
    if _has_copilot_chat_marker(table_name):
        return True
    for index, value in enumerate(row):
        if index == payload_column:
            continue
        if index == 0 and id_column_index != 0:
            continue
        if _has_copilot_chat_marker(str(value or "")):
            return True
    return False


def _has_copilot_chat_marker(value: str) -> bool:
    return bool(_COPILOT_CHAT_MARKER.search(value))


def _quote_identifier(value: str) -> str:
    escaped = value.replace('"', '""')
    return f'"{escaped}"'


def _try_load_json(raw: object) -> object | None:
    if not isinstance(raw, (str, bytes, bytearray)):
        return None
    text = _decode_bytes(raw)
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def _decode_bytes(raw: object) -> str:
    if isinstance(raw, bytes | bytearray):
        return raw.decode("utf-8", errors="replace")
    return str(raw)
