"""Application service for Anamnesis workflows."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
from typing import Any

from .authorization import AuthorizationStore
from .discovery import discover_sources, iter_source_files
from .filesystem import (
    PRIVATE_DIR_MODE,
    PRIVATE_FILE_MODE,
    ensure_private_directory,
    ensure_private_file,
    file_mode,
    format_mode,
)
from .index import AnamnesisIndex
from .models import (
    DiscoveredSource,
    SearchResult,
    SourceAuthorization,
    SourceDefinition,
    SourceIndexStatus,
    policy_id_for_snapshot,
    policy_snapshot_for_definition,
)
from .parsers import SessionParseError, parse_session_file
from .registry import definitions_by_definition_id, definitions_by_source_type


class AnamnesisService:
    """Coordinates discovery, authorization, indexing, and search."""

    def __init__(self, workspace_root: Path | None = None, *, home: Path | None = None) -> None:
        self.workspace_root = (workspace_root or Path.home() / ".anamnesis").expanduser()
        self.home = home or Path.home()
        self.authorization_store = AuthorizationStore(
            self.workspace_root / "sources.authorization.json"
        )
        self.index = AnamnesisIndex(self.workspace_root / "anamnesis.sqlite")

    def discover(self) -> tuple[DiscoveredSource, ...]:
        return discover_sources(
            home=self.home,
            authorization_store=self.authorization_store,
        )

    def authorize(
        self,
        source_id: str,
        *,
        policy_snapshot: dict[str, Any] | None = None,
        policy_mode: str = "current",
        policy_id: str | None = None,
        authorized_at: str | None = None,
    ) -> SourceAuthorization:
        source = self._source_by_id(source_id)
        source_definition = definitions_by_source_type().get(source.source_type)
        if policy_snapshot is None and source_definition is not None:
            policy_snapshot = policy_snapshot_for_definition(source_definition)
        if policy_id is None:
            if policy_snapshot is not None:
                policy_id = policy_id_for_snapshot(policy_snapshot)
            else:
                policy_id = source.definition_id
        return self.authorization_store.authorize(
            source,
            policy_id=policy_id,
            policy_snapshot=policy_snapshot or {},
            policy_mode=policy_mode,
            authorized_at=authorized_at or _now_utc_iso(),
        )

    def revoke(self, source_id: str) -> int:
        self.authorization_store.revoke(source_id)
        return self.index.purge_source(source_id)

    def index_authorized_sources(self) -> dict[str, Any]:
        counts: dict[str, Any] = {"documents": 0, "chunks": 0, "sources": 0}
        skipped_file_diagnostics: list[dict[str, str]] = []
        source_error_diagnostics: list[dict[str, str]] = []
        source_definitions_by_type = definitions_by_source_type()
        source_definitions_by_id = definitions_by_definition_id()
        needs_compaction = False
        for authorization in self.authorization_store.authorized_sources():
            counts["sources"] += 1
            source_definition = source_definitions_by_type.get(
                authorization.source_type
            )
            if source_definition is None:
                source_error_diagnostics.append(
                    {
                        "source_id": authorization.source_id,
                        "path": str(authorization.path),
                        "reason": f"unknown_source_definition: {authorization.source_type}",
                    }
                )
                continue

            policy_snapshot = authorization.policy_snapshot
            policy_id = authorization.policy_id or authorization.definition_id
            ignored_files_due_to_policy_restriction = 0
            effective_file_suffixes = source_definition.file_suffixes
            if authorization.policy_mode == "legacy" and policy_snapshot:
                effective_file_suffixes = self._suffixes_from_snapshot(
                    policy_snapshot.get("file_suffixes", ())
                )
                ignored_files_due_to_policy_restriction = (
                    self._count_ignored_policy_files(
                        authorization,
                        source_definition,
                        effective_file_suffixes,
                    )
                )
            else:
                if policy_id:
                    registered_definition = source_definitions_by_id.get(policy_id)
                    if registered_definition is None:
                        source_error_diagnostics.append(
                    {
                        "source_id": authorization.source_id,
                        "path": str(authorization.path),
                        "reason": (
                                    "source_policy_drift: "
                                    f"unknown_definition_id={policy_id}"
                                ),
                        }
                    )
                        continue
                    if registered_definition.definition_id != source_definition.definition_id:
                        source_error_diagnostics.append(
                    {
                        "source_id": authorization.source_id,
                        "path": str(authorization.path),
                        "reason": (
                                    "source_policy_drift: "
                                    f"unknown_definition_id={policy_id}"
                                ),
                        }
                    )
                        continue
                effective_file_suffixes = self._suffixes_from_snapshot(
                    policy_snapshot_for_definition(source_definition).get("file_suffixes", ())
                )

            if not effective_file_suffixes:
                source_error_diagnostics.append(
                    {
                        "source_id": authorization.source_id,
                        "path": str(authorization.path),
                        "reason": "source_policy_snapshot_invalid: file_suffixes missing",
                    }
                )
                continue

            source_files = iter_source_files(
                authorization.path,
                effective_file_suffixes,
                source_type=authorization.source_type,
            )
            source_documents = []
            source_parser_mode = "structured"
            source_drift_detected = False
            source_last_status = "success"
            for path in source_files:
                try:
                    parsed_file = parse_session_file(
                        path,
                        source_id=authorization.source_id,
                        source_type=authorization.source_type,
                    )
                except SessionParseError as exc:
                    if exc.reason.startswith("schema_drift:"):
                        source_last_status = "drift_error"
                        source_drift_detected = True
                    skipped_file_diagnostics.append(
                        {"path": str(exc.path), "reason": exc.reason}
                    )
                    if source_last_status == "drift_error":
                        break
                    continue
                except (OSError, UnicodeDecodeError, ValueError) as exc:
                    skipped_file_diagnostics.append(
                        {"path": str(path), "reason": type(exc).__name__}
                    )
                    continue
                except Exception as exc:
                    source_last_status = "parse_error"
                    source_error_diagnostics.append(
                        {
                            "source_id": authorization.source_id,
                            "path": str(path),
                            "reason": f"unexpected_parse_error: {type(exc).__name__}",
                        }
                    )
                    break
                if parsed_file.parser_mode == "raw_text":
                    source_parser_mode = "raw_text"
                if parsed_file.drift_detected:
                    source_last_status = "drift_error"
                    source_drift_detected = True
                    break
                source_documents.extend(parsed_file.documents)
            if source_last_status in {"drift_error", "parse_error"}:
                now_iso = _now_utc_iso()
                effective_mode = (
                    "failed" if source_last_status != "success" else source_parser_mode
                )
                try:
                    self.index.update_source_status(
                        authorization,
                        last_index_status=source_last_status,
                        drift_detected=source_drift_detected,
                        parser_mode=effective_mode,
                        ignored_files_due_to_policy_restriction=(
                            ignored_files_due_to_policy_restriction
                        ),
                        last_indexed_at=now_iso,
                    )
                except sqlite3.Error as exc:
                    source_error_diagnostics.append(
                        {
                            "source_id": authorization.source_id,
                            "path": str(authorization.path),
                            "reason": f"index_write_error: {type(exc).__name__}: {exc}",
                        }
                    )
                continue
            documents_tuple = tuple(source_documents)
            now_iso = _now_utc_iso()
            try:
                replaced_chunks = self.index.replace_source_documents(
                    authorization,
                    documents_tuple,
                    last_index_status=source_last_status,
                    drift_detected=source_drift_detected,
                    parser_mode=source_parser_mode,
                    ignored_files_due_to_policy_restriction=(
                        ignored_files_due_to_policy_restriction
                    ),
                    last_indexed_at=now_iso,
                )
            except sqlite3.Error as exc:
                source_error_diagnostics.append(
                    {
                        "source_id": authorization.source_id,
                        "path": str(authorization.path),
                        "reason": f"index_write_error: {type(exc).__name__}: {exc}",
                    }
                )
                continue
            counts["documents"] += len(documents_tuple)
            counts["chunks"] += replaced_chunks
            needs_compaction = True
        if needs_compaction:
            self.index.vacuum()
        if skipped_file_diagnostics:
            counts["skipped_files"] = len(skipped_file_diagnostics)
            counts["skipped_file_diagnostics"] = skipped_file_diagnostics
        if source_error_diagnostics:
            counts["source_errors"] = len(source_error_diagnostics)
            counts["source_error_diagnostics"] = source_error_diagnostics
        return counts

    def status(self) -> dict[str, Any]:
        statuses_by_id = {
            status.source_id: status
            for status in self.index.source_statuses()
        }
        authorizations_by_id = {
            authorization.source_id: authorization
            for authorization in self.authorization_store.authorizations.values()
        }
        discovered_sources = self.discover()
        source_rows: list[dict[str, Any]] = []
        for discovered in discovered_sources:
            status = statuses_by_id.get(discovered.source_id)
            authorization = authorizations_by_id.get(discovered.source_id)
            last_status = "not_indexed"
            parser_mode = "n/a"
            drift_detected = False
            ignored_files_due_to_policy_restriction = 0
            last_indexed_at = None
            policy_id = ""
            policy_mode = ""
            policy_snapshot = {}
            if status is not None:
                last_status = status.last_index_status or "not_indexed"
                parser_mode = status.parser_mode or "unknown"
                drift_detected = status.drift_detected
                last_indexed_at = status.last_indexed_at
                ignored_files_due_to_policy_restriction = (
                    status.ignored_files_due_to_policy_restriction
                )
            if not discovered.authorized:
                last_status = "not_authorized"
                parser_mode = parser_mode if status else "n/a"
                policy_mode = "not_authorized"
            elif authorization is not None:
                policy_id = authorization.policy_id or authorization.definition_id
                policy_mode = authorization.policy_mode
                policy_snapshot = authorization.policy_snapshot
            source_rows.append(
                {
                    "source_id": discovered.source_id,
                    "source_type": discovered.source_type,
                    "display_name": discovered.display_name,
                    "path": str(discovered.path),
                    "authorized": discovered.authorized,
                    "last_indexed_at": last_indexed_at,
                    "status": last_status,
                    "parser_mode": parser_mode,
                    "drift_detected": drift_detected,
                    "ignored_files_due_to_policy_restriction": ignored_files_due_to_policy_restriction,
                    "policy_id": policy_id,
                    "policy_mode": policy_mode,
                    "policy_snapshot": policy_snapshot,
                }
            )
        return {"sources": source_rows}

    def sync_health(self, *, stale_after_days: int = 30) -> dict[str, Any]:
        thresholds = datetime.now(timezone.utc) - timedelta(days=stale_after_days)
        statuses_by_id = {
            status.source_id: status
            for status in self.index.source_statuses()
        }
        issues: list[dict[str, str]] = []
        ignored_files_due_to_policy_restriction = 0
        for source in self.authorization_store.authorized_sources():
            status = statuses_by_id.get(source.source_id)
            if status is None:
                issues.append(
                    {
                        "source_id": source.source_id,
                        "reason": "not_indexed",
                    }
                )
                continue
            if status.ignored_files_due_to_policy_restriction:
                ignored_files_due_to_policy_restriction += (
                    status.ignored_files_due_to_policy_restriction
                )
                issues.append(
                    {
                        "source_id": source.source_id,
                        "reason": "policy_restriction",
                        "count": str(status.ignored_files_due_to_policy_restriction),
                    }
                )
                continue
            if status.last_index_status == "drift_error":
                issues.append(
                    {
                        "source_id": source.source_id,
                        "reason": "drift_error",
                    }
                )
                continue
            if status.last_index_status == "parse_error":
                issues.append(
                    {
                        "source_id": source.source_id,
                        "reason": "parse_error",
                    }
                )
                continue
            if status.drift_detected:
                issues.append(
                    {
                        "source_id": source.source_id,
                        "reason": "drift_detected",
                    }
                )
                continue
            parsed_last_indexed_at = _parse_indexed_at(status.last_indexed_at)
            if not status.last_indexed_at or parsed_last_indexed_at is None:
                issues.append(
                    {
                        "source_id": source.source_id,
                        "reason": "not_recent",
                    }
                )
                continue
            if parsed_last_indexed_at < thresholds:
                issues.append(
                    {
                        "source_id": source.source_id,
                        "reason": "not_recent",
                    }
                )
                continue
            if status.parser_mode == "raw_text":
                issues.append(
                    {
                        "source_id": source.source_id,
                        "reason": "raw_text_fallback",
                    }
                )
        return {
            "issues": issues,
            "has_issues": bool(issues),
            "ignored_files_due_to_policy_restriction": ignored_files_due_to_policy_restriction,
        }

    def search(self, query: str, *, limit: int = 10) -> tuple[SearchResult, ...]:
        return self.index.search(query, limit=limit)

    def privacy_audit(self, *, fix_permissions: bool = False) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []
        warnings: list[dict[str, str]] = []
        fixed: list[dict[str, str]] = []

        workspace = self.workspace_root
        authorization_path = self.authorization_store.path
        database_path = self.index.path
        sidecar_paths = (
            Path(f"{database_path}-wal"),
            Path(f"{database_path}-shm"),
            Path(f"{database_path}-journal"),
        )

        self._audit_mode(
            checks,
            fixed,
            path=workspace,
            expected_mode=PRIVATE_DIR_MODE,
            check_id="workspace_mode",
            kind="directory",
            fix_permissions=fix_permissions,
        )
        self._audit_mode(
            checks,
            fixed,
            path=authorization_path,
            expected_mode=PRIVATE_FILE_MODE,
            check_id="authorization_file_mode",
            kind="file",
            fix_permissions=fix_permissions,
        )
        self._audit_mode(
            checks,
            fixed,
            path=database_path,
            expected_mode=PRIVATE_FILE_MODE,
            check_id="database_file_mode",
            kind="file",
            fix_permissions=fix_permissions,
        )
        for sidecar_path in sidecar_paths:
            self._audit_mode(
                checks,
                fixed,
                path=sidecar_path,
                expected_mode=PRIVATE_FILE_MODE,
                check_id="sqlite_sidecar_mode",
                kind="file",
                fix_permissions=fix_permissions,
            )

        if database_path.exists():
            secure_delete_ok = self.index.secure_delete_enabled()
            checks.append(
                {
                    "id": "sqlite_secure_delete",
                    "ok": secure_delete_ok,
                    "path": str(database_path),
                    "expected": "1",
                    "actual": "1" if secure_delete_ok else "0",
                }
            )
            warnings.append(
                {
                    "id": "plaintext_sqlite",
                    "path": str(database_path),
                    "message": (
                        "anamnesis.sqlite is plaintext searchable SQLite; "
                        "secure_delete, VACUUM, and restrictive permissions do "
                        "not provide encryption-at-rest."
                    ),
                }
            )

        return {
            "ok": all(check["ok"] for check in checks),
            "checks": checks,
            "warnings": warnings,
            "fixed": fixed,
        }

    def _source_by_id(self, source_id: str) -> DiscoveredSource:
        for source in self.discover():
            if source.source_id == source_id:
                return source
        raise KeyError(f"unknown source_id: {source_id}")

    def _suffixes_from_snapshot(self, suffixes: Any) -> tuple[str, ...]:
        values = []
        for value in suffixes or ():
            if not isinstance(value, str):
                continue
            values.append(value)
        return tuple(sorted(set(values)))

    def _count_ignored_policy_files(
        self,
        authorization: SourceAuthorization,
        source_definition: SourceDefinition,
        effective_suffixes: tuple[str, ...],
    ) -> int:
        current_suffixes = source_definition.file_suffixes
        if not effective_suffixes:
            return 0
        if not current_suffixes:
            return 0
        all_files = set(
            iter_source_files(
                authorization.path,
                current_suffixes,
                source_type=authorization.source_type,
            )
        )
        effective_files = set(
            iter_source_files(
                authorization.path,
                effective_suffixes,
                source_type=authorization.source_type,
            )
        )
        return len(all_files - effective_files)

    def _audit_mode(
        self,
        checks: list[dict[str, Any]],
        fixed: list[dict[str, str]],
        *,
        path: Path,
        expected_mode: int,
        check_id: str,
        kind: str,
        fix_permissions: bool,
    ) -> None:
        existed = path.exists()
        actual_mode = file_mode(path) if existed else None
        if existed and actual_mode != expected_mode and fix_permissions:
            if kind == "directory":
                ensure_private_directory(path)
            else:
                ensure_private_file(path)
            fixed.append(
                {
                    "id": check_id,
                    "path": str(path),
                    "mode": format_mode(expected_mode) or "",
                }
            )
            actual_mode = file_mode(path)
        checks.append(
            {
                "id": check_id,
                "ok": (not existed) or actual_mode == expected_mode,
                "path": str(path),
                "present": existed,
                "expected_mode": format_mode(expected_mode),
                "actual_mode": format_mode(actual_mode),
            }
        )


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_indexed_at(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None
