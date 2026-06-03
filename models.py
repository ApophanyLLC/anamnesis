"""Core data models for Anamnesis."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SourceDefinition:
    """Governed capability record for a known AI session source."""

    source_type: str
    display_name: str
    default_path: Path
    file_suffixes: tuple[str, ...]
    access_method: str
    default_discovery_policy: str
    accepted_file_shapes: tuple[str, ...]
    risk_level: str
    parser_owner: str
    storage_model: str = ""
    local_path_format: str = ""
    user_access_steps: tuple[str, ...] = ()
    confidence_level: str = "unknown"
    drift_warning: str = ""
    notes: str = ""
    definition_id: str = ""

    def __post_init__(self) -> None:
        if not self.definition_id:
            object.__setattr__(self, "definition_id", _source_definition_id(self))


@dataclass(frozen=True)
class DiscoveredSource:
    """Inventory-only summary of a source on disk."""

    source_id: str
    source_type: str
    display_name: str
    path: Path
    access_method: str
    default_discovery_policy: str
    accepted_file_shapes: tuple[str, ...]
    risk_level: str
    parser_owner: str
    storage_model: str
    local_path_format: str
    user_access_steps: tuple[str, ...]
    confidence_level: str
    drift_warning: str
    definition_id: str
    file_count: int
    total_bytes: int
    first_modified_at: datetime | None
    last_modified_at: datetime | None
    authorized: bool
    notes: str = ""


@dataclass(frozen=True)
class SourceAuthorization:
    """Persistent user consent record for a discovered source."""

    source_id: str
    source_type: str
    display_name: str
    path: Path
    authorized: bool
    definition_id: str = ""


@dataclass(frozen=True)
class Exchange:
    """A normalized exchange chunk extracted from a session."""

    role: str
    text: str
    created_at: str | None = None


@dataclass(frozen=True)
class SessionDocument:
    """Normalized session document ready for indexing."""

    source_id: str
    source_type: str
    session_id: str
    path: Path
    title: str
    created_at: str | None
    modified_at: str | None
    exchanges: tuple[Exchange, ...]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class SearchResult:
    """Search hit returned from the local index."""

    source_id: str
    source_type: str
    session_id: str
    title: str
    path: str
    role: str
    text: str
    score: float


def _source_definition_id(definition: SourceDefinition) -> str:
    payload = {
        "accepted_file_shapes": list(definition.accepted_file_shapes),
        "access_method": definition.access_method,
        "confidence_level": definition.confidence_level,
        "default_discovery_policy": definition.default_discovery_policy,
        "default_path": str(definition.default_path),
        "display_name": definition.display_name,
        "drift_warning": definition.drift_warning,
        "file_suffixes": list(definition.file_suffixes),
        "local_path_format": definition.local_path_format,
        "notes": definition.notes,
        "parser_owner": definition.parser_owner,
        "risk_level": definition.risk_level,
        "source_type": definition.source_type,
        "storage_model": definition.storage_model,
        "user_access_steps": list(definition.user_access_steps),
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"{definition.source_type}:{digest[:16]}"
