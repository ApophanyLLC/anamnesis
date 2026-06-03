"""Inventory-only source discovery for known AI session stores."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import zipfile

from .authorization import AuthorizationStore
from .models import DiscoveredSource, SourceDefinition
from .registry import DEFAULT_SOURCE_DEFINITIONS


def source_id_for(source_type: str, path: Path) -> str:
    canonical = str(path.expanduser().resolve() if path.exists() else path.expanduser())
    digest = hashlib.sha256(f"{source_type}:{canonical}".encode("utf-8")).hexdigest()
    return f"{source_type}:{digest[:16]}"


def discover_sources(
    *,
    home: Path | None = None,
    authorization_store: AuthorizationStore | None = None,
    definitions: tuple[SourceDefinition, ...] = DEFAULT_SOURCE_DEFINITIONS,
) -> tuple[DiscoveredSource, ...]:
    """Return inventory summaries without opening session files."""

    base_home = home or Path.home()
    discovered: list[DiscoveredSource] = []
    authorizations = authorization_store.authorizations if authorization_store else {}

    for definition in definitions:
        path = _expand_default_path(definition.default_path, base_home)
        source_id = source_id_for(definition.source_type, path)
        files = _candidate_files(
            path,
            definition.file_suffixes,
            source_type=definition.source_type,
        )
        stats = [_safe_stat(file_path) for file_path in files]
        stats = [item for item in stats if item is not None]
        modified_times = [item.st_mtime for item in stats]
        authorization = authorizations.get(source_id)
        discovered.append(
            DiscoveredSource(
                source_id=source_id,
                source_type=definition.source_type,
                display_name=definition.display_name,
                path=path,
                access_method=definition.access_method,
                default_discovery_policy=definition.default_discovery_policy,
                accepted_file_shapes=definition.accepted_file_shapes,
                risk_level=definition.risk_level,
                parser_owner=definition.parser_owner,
                storage_model=definition.storage_model,
                local_path_format=definition.local_path_format,
                user_access_steps=definition.user_access_steps,
                confidence_level=definition.confidence_level,
                drift_warning=definition.drift_warning,
                definition_id=definition.definition_id,
                file_count=len(stats),
                total_bytes=sum(item.st_size for item in stats),
                first_modified_at=_from_timestamp(min(modified_times))
                if modified_times
                else None,
                last_modified_at=_from_timestamp(max(modified_times))
                if modified_times
                else None,
                authorized=bool(authorization and authorization.authorized),
                notes=definition.notes,
            )
        )

    return tuple(discovered)


def iter_source_files(
    path: Path,
    suffixes: tuple[str, ...],
    *,
    source_type: str | None = None,
) -> tuple[Path, ...]:
    return _candidate_files(path, suffixes, source_type=source_type)


def _candidate_files(
    path: Path,
    suffixes: tuple[str, ...],
    *,
    source_type: str | None = None,
) -> tuple[Path, ...]:
    expanded = path.expanduser()
    if expanded.is_file():
        return (
            (expanded,)
            if expanded.suffix.lower() in suffixes
            and _source_file_is_eligible(expanded, source_type=source_type)
            else ()
        )
    if not expanded.exists() or not expanded.is_dir():
        return ()
    return tuple(
        sorted(
            candidate
            for candidate in expanded.rglob("*")
            if candidate.is_file()
            and candidate.suffix.lower() in suffixes
            and _source_file_is_eligible(candidate, source_type=source_type)
        )
    )


def _source_file_is_eligible(path: Path, *, source_type: str | None) -> bool:
    if source_type != "chatgpt_export":
        return True
    suffix = path.suffix.lower()
    if suffix == ".json":
        return path.name == "conversations.json"
    if suffix == ".zip":
        return _zip_contains_chatgpt_conversations(path)
    return False


def _zip_contains_chatgpt_conversations(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as archive:
            return any(_is_chatgpt_conversations_member(name) for name in archive.namelist())
    except (OSError, zipfile.BadZipFile):
        return False


def _is_chatgpt_conversations_member(name: str) -> bool:
    return Path(name).name == "conversations.json"


def _expand_default_path(path: Path, home: Path) -> Path:
    text = str(path)
    if text == "~":
        return home
    if text.startswith("~/"):
        return home / text[2:]
    return path.expanduser()


def _safe_stat(path: Path):
    try:
        return path.stat()
    except OSError:
        return None


def _from_timestamp(timestamp: float) -> datetime:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)
