"""Shared parser helpers for Anamnesis session documents."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path

from .models import Exchange, SessionDocument


MAX_TEXT_CHUNK_CHARS = 4000
TEXT_CHUNK_OVERLAP_CHARS = 250


class SessionParseError(ValueError):
    """Raised when a candidate source file cannot be parsed safely."""

    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(reason)


def documents_from_payload(
    payload: object,
    *,
    source_id: str,
    source_type: str,
    path: Path,
    fallback_session_id: str,
) -> tuple[SessionDocument, ...]:
    if isinstance(payload, list):
        documents = []
        for index, item in enumerate(payload):
            if isinstance(item, dict):
                documents.extend(
                    documents_from_payload(
                        item,
                        source_id=source_id,
                        source_type=source_type,
                        path=path,
                        fallback_session_id=f"{fallback_session_id}:{index}",
                    )
                )
        return tuple(documents)

    if not isinstance(payload, dict):
        return ()

    conversations = payload.get("conversations")
    if isinstance(conversations, list):
        documents: list[SessionDocument] = []
        for index, item in enumerate(conversations):
            if isinstance(item, dict):
                documents.extend(
                    documents_from_payload(
                        item,
                        source_id=source_id,
                        source_type=source_type,
                        path=path,
                        fallback_session_id=f"{fallback_session_id}:{index}",
                    )
                )
        return tuple(documents)

    exchanges = tuple(extract_exchanges(payload))
    if not exchanges:
        text = text_from_node(payload)
        if text:
            exchanges = (Exchange(role="document", text=text),)
    if not exchanges:
        return ()

    session_id = str(
        payload.get("id")
        or payload.get("session_id")
        or payload.get("conversation_id")
        or fallback_session_id
    )
    title = str(payload.get("title") or payload.get("name") or session_id)
    return (
        build_document(
            path,
            source_id=source_id,
            source_type=source_type,
            session_id=session_id,
            title=title,
            created_at=coerce_datetime_text(payload),
            exchanges=exchanges,
            metadata={"raw_keys": sorted(str(key) for key in payload.keys())},
        ),
    )


def extract_exchanges(payload: dict[str, object]) -> list[Exchange]:
    for key in ("messages", "entries", "turns", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            exchanges = [exchange_from_item(item) for item in value]
            return [item for item in exchanges if item is not None]

    mapping = payload.get("mapping")
    if isinstance(mapping, dict):
        return extract_mapping_exchanges(mapping)

    return []


def extract_mapping_exchanges(mapping: dict[object, object]) -> list[Exchange]:
    """Traverse ChatGPT-style mapping nodes in parent/child conversation order."""

    nodes = {str(key): value for key, value in mapping.items() if isinstance(value, dict)}
    if not nodes:
        return []

    child_ids: set[str] = set()
    for node in nodes.values():
        children = node.get("children")
        if isinstance(children, list):
            child_ids.update(str(child_id) for child_id in children)

    roots = [
        node_id
        for node_id, node in nodes.items()
        if not node.get("parent") or str(node.get("parent")) not in nodes
    ]
    if not roots:
        roots = [node_id for node_id in nodes if node_id not in child_ids] or list(nodes)

    exchanges: list[Exchange] = []
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visited:
            return
        node = nodes.get(node_id)
        if node is None:
            return
        visited.add(node_id)

        message = node.get("message")
        if isinstance(message, dict):
            exchange = exchange_from_item(message)
            if exchange is not None:
                exchanges.append(exchange)

        children = node.get("children")
        if isinstance(children, list):
            for child_id in children:
                visit(str(child_id))

    for root_id in roots:
        visit(root_id)
    for node_id in nodes:
        visit(node_id)

    return exchanges


def exchange_from_item(item: object) -> Exchange | None:
    if isinstance(item, str):
        text = item.strip()
        return Exchange(role="unknown", text=text) if text else None
    if not isinstance(item, dict):
        return None

    role = item.get("role")
    author = item.get("author")
    if isinstance(author, dict):
        role = role or author.get("role") or author.get("name")

    text = text_from_node(item)
    if not text:
        return None
    return Exchange(
        role=str(role or item.get("type") or "unknown"),
        text=text,
        created_at=coerce_datetime_text(item),
    )


def text_from_node(node: object) -> str:
    if isinstance(node, str):
        return node.strip()
    if isinstance(node, list):
        return "\n".join(filter(None, (text_from_node(item) for item in node))).strip()
    if not isinstance(node, dict):
        return ""

    for key in ("text", "content", "message", "body", "value"):
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list):
            text = text_from_node(value)
            if text:
                return text
        if isinstance(value, dict):
            text = text_from_node(value)
            if text:
                return text

    parts = node.get("parts")
    if isinstance(parts, list):
        return text_from_node(parts)

    return ""


def coerce_datetime_text(payload: dict[str, object]) -> str | None:
    for key in ("created_at", "create_time", "timestamp", "time", "date"):
        value = payload.get(key)
        if value is None:
            continue
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
        text = str(value).strip()
        if text:
            return text
    return None


def fallback_document(
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


def text_document_exchanges(text: str) -> tuple[Exchange, ...]:
    chunks = tuple(chunk_text(text))
    if not chunks:
        return ()
    return tuple(Exchange(role="document", text=chunk) for chunk in chunks)


def chunk_text(
    text: str,
    *,
    max_chars: int = MAX_TEXT_CHUNK_CHARS,
    overlap_chars: int = TEXT_CHUNK_OVERLAP_CHARS,
) -> tuple[str, ...]:
    normalized = text.strip()
    if not normalized:
        return ()
    if len(normalized) <= max_chars:
        return (normalized,)

    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        hard_end = min(start + max_chars, len(normalized))
        end = _chunk_boundary(normalized, start=start, hard_end=hard_end)
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start = max(end - overlap_chars, start + 1)
    return tuple(chunks)


def _chunk_boundary(text: str, *, start: int, hard_end: int) -> int:
    if hard_end >= len(text):
        return len(text)
    boundary_floor = start + (hard_end - start) // 2
    candidates = (
        text.rfind("\n\n", boundary_floor, hard_end),
        text.rfind("\n", boundary_floor, hard_end),
        text.rfind(". ", boundary_floor, hard_end),
        text.rfind(" ", boundary_floor, hard_end),
    )
    return max(candidates) + 1 if max(candidates) >= boundary_floor else hard_end


def build_document(
    path: Path,
    *,
    source_id: str,
    source_type: str,
    session_id: str,
    title: str,
    created_at: str | None,
    exchanges: tuple[Exchange, ...],
    metadata: dict[str, object],
) -> SessionDocument:
    modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
    return SessionDocument(
        source_id=source_id,
        source_type=source_type,
        session_id=session_id,
        path=path,
        title=title,
        created_at=created_at,
        modified_at=modified_at,
        exchanges=exchanges,
        metadata=dict(metadata),
    )


def fallback_session_id_for(path: Path, *, source_id: str, suffix: str | None = None) -> str:
    canonical_path = str(path.expanduser().resolve() if path.exists() else path.expanduser())
    hash_input = f"{source_id}:{canonical_path}"
    if suffix:
        hash_input = f"{hash_input}:{suffix}"
    digest = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
    return f"{path.stem}:{digest[:16]}"
