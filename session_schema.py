"""Canonical session schema for adapter outputs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class StandardExchange:
    """Single normalized message exchange within one session."""

    timestamp: str | None
    role: str
    content: str


@dataclass(frozen=True)
class StandardSession:
    """Canonical exchange document shape consumed by core indexing logic."""

    session_id: str
    source_id: str
    source_type: str
    title: str
    created_at: str | None
    modified_at: str | None
    exchanges: tuple[StandardExchange, ...]
    metadata: dict[str, Any]


def to_session_document(session: StandardSession, path: Path) -> "SessionDocument":
    """Convert a canonical schema session into a runtime search document."""

    from .models import Exchange, SessionDocument

    return SessionDocument(
        source_id=session.source_id,
        source_type=session.source_type,
        session_id=session.session_id,
        path=path,
        title=session.title,
        created_at=session.created_at,
        modified_at=session.modified_at,
        exchanges=tuple(
            Exchange(
                role=exchange.role,
                text=exchange.content,
                created_at=exchange.timestamp,
            )
            for exchange in session.exchanges
        ),
        metadata=dict(session.metadata),
    )


def from_session_document(document: "SessionDocument") -> StandardSession:
    """Convert a runtime document into canonical schema for adapter authors."""

    return StandardSession(
        session_id=document.session_id,
        source_id=document.source_id,
        source_type=document.source_type,
        title=document.title,
        created_at=document.created_at,
        modified_at=document.modified_at,
        exchanges=tuple(
            StandardExchange(exchange.timestamp, exchange.role, exchange.text)
            for exchange in document.exchanges
        ),
        metadata=dict(document.metadata),
    )
