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
        discovered_sources_by_id = {source.source_id: source for source in self.discover()}
        existing_statuses_by_id = {
            status.source_id: status for status in self.index.source_statuses()
        }
        needs_compaction = False
        for authorization in self.authorization_store.authorized_sources():
            counts["sources"] += 1
            now_iso = _now_utc_iso()
            discovered_source = discovered_sources_by_id.get(authorization.source_id)
            source_definition = source_definitions_by_type.get(
                authorization.source_type
            )
            source_error_summary = self._empty_error_summary()
            source_sync_warnings: list[str] = []
            if source_definition is None:
                reason = f"unknown_source_definition: {authorization.source_type}"
                source_error_diagnostics.append(
                    {
                        "source_id": authorization.source_id,
                        "path": str(authorization.path),
                        "reason": reason,
                    }
                )
                source_error_summary = self._increment_error_summary(
                    source_error_summary,
                    "policy_drift",
                )
                self._persist_source_status(
                    authorization=authorization,
                    now_iso=now_iso,
                    source_last_status="drift_error",
                    source_drift_detected=True,
                    source_parser_mode="failed",
                    source_error_summary=source_error_summary,
                    statuses_by_id=existing_statuses_by_id,
                    ignored_files_due_to_policy_restriction=0,
                    sync_warnings=source_sync_warnings,
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
                        reason = (
                            "source_policy_drift: "
                            f"unknown_definition_id={policy_id}"
                        )
                        source_error_diagnostics.append(
                            {
                                "source_id": authorization.source_id,
                                "path": str(authorization.path),
                                "reason": reason,
                            }
                        )
                        source_error_summary = self._increment_error_summary(
                            source_error_summary, "policy_drift"
                        )
                        self._persist_source_status(
                            authorization=authorization,
                            now_iso=now_iso,
                            source_last_status="drift_error",
                            source_drift_detected=True,
                            source_parser_mode="failed",
                            source_error_summary=source_error_summary,
                            statuses_by_id=existing_statuses_by_id,
                            ignored_files_due_to_policy_restriction=0,
                            sync_warnings=source_sync_warnings,
                        )
                        continue
                    if registered_definition.definition_id != source_definition.definition_id:
                        reason = (
                            "source_policy_drift: "
                            f"unknown_definition_id={policy_id}"
                        )
                        source_error_diagnostics.append(
                            {
                                "source_id": authorization.source_id,
                                "path": str(authorization.path),
                                "reason": reason,
                            }
                        )
                        source_error_summary = self._increment_error_summary(
                            source_error_summary, "policy_drift"
                        )
                        self._persist_source_status(
                            authorization=authorization,
                            now_iso=now_iso,
                            source_last_status="drift_error",
                            source_drift_detected=True,
                            source_parser_mode="failed",
                            source_error_summary=source_error_summary,
                            statuses_by_id=existing_statuses_by_id,
                            ignored_files_due_to_policy_restriction=0,
                            sync_warnings=source_sync_warnings,
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
                source_error_summary = self._increment_error_summary(
                    source_error_summary, "policy_drift"
                )
                self._persist_source_status(
                    authorization=authorization,
                    now_iso=now_iso,
                    source_last_status="drift_error",
                    source_drift_detected=True,
                    source_parser_mode="failed",
                    source_error_summary=source_error_summary,
                    statuses_by_id=existing_statuses_by_id,
                    ignored_files_due_to_policy_restriction=0,
                    sync_warnings=source_sync_warnings,
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
            parsed_file_count = 0
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
                        source_error_summary = self._increment_error_summary(
                            source_error_summary, "schema_drift"
                        )
                    else:
                        source_error_summary = self._increment_error_summary(
                            source_error_summary, "parse_errors"
                        )
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
                    source_error_summary = self._increment_error_summary(
                        source_error_summary, "parse_errors"
                    )
                    continue
                except Exception as exc:
                    source_last_status = "parse_error"
                    source_error_summary = self._increment_error_summary(
                        source_error_summary, "parse_errors"
                    )
                    source_error_diagnostics.append(
                        {
                            "source_id": authorization.source_id,
                            "path": str(path),
                            "reason": f"unexpected_parse_error: {type(exc).__name__}",
                        }
                    )
                    break
                if parsed_file.parser_mode == "raw_text":
                    source_parser_mode = "fallback_text"
                parsed_file_count += len(parsed_file.documents)
                if parsed_file.drift_detected:
                    source_last_status = "drift_error"
                    source_drift_detected = True
                    break
                source_documents.extend(parsed_file.documents)
            source_last_modified_at = (
                discovered_source.last_modified_at if discovered_source else None
            )
            existing_status = existing_statuses_by_id.get(authorization.source_id)
            existing_last_indexed_at = (
                _parse_indexed_at(existing_status.last_indexed_at)
                if existing_status is not None
                else None
            )
            if (
                source_last_modified_at is not None
                and existing_last_indexed_at is not None
                and (source_last_modified_at - existing_last_indexed_at).total_seconds()
                > 24 * 60 * 60
                and parsed_file_count == 0
            ):
                source_sync_warnings.append(
                    (
                        f"Source '{authorization.source_id}' has been modified on disk "
                        "but 0 documents were parsed"
                    )
                )
            if source_last_status in {"drift_error", "parse_error"}:
                now_iso = _now_utc_iso()
                effective_mode = (
                    "failed" if source_last_status != "success" else source_parser_mode
                )
                try:
                    self._persist_source_status(
                        authorization,
                        now_iso=now_iso,
                        source_last_status=source_last_status,
                        source_drift_detected=source_drift_detected,
                        source_parser_mode=effective_mode,
                        source_error_summary=source_error_summary,
                        statuses_by_id=existing_statuses_by_id,
                        ignored_files_due_to_policy_restriction=(
                            ignored_files_due_to_policy_restriction
                        ),
                        sync_warnings=source_sync_warnings,
                    )
                except sqlite3.Error as exc:
                    source_error_summary = self._increment_error_summary(
                        source_error_summary,
                        "other_errors",
                    )
                    source_error_diagnostics.append(
                        {
                            "source_id": authorization.source_id,
                            "path": str(authorization.path),
                            "reason": f"index_write_error: {type(exc).__name__}: {exc}",
                        }
                    )
                    self._persist_source_status(
                        authorization=authorization,
                        now_iso=now_iso,
                        source_last_status="parse_error",
                        source_drift_detected=source_drift_detected,
                        source_parser_mode="failed",
                        source_error_summary=source_error_summary,
                        statuses_by_id=existing_statuses_by_id,
                        ignored_files_due_to_policy_restriction=(
                            ignored_files_due_to_policy_restriction
                        ),
                        sync_warnings=source_sync_warnings,
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
                    error_count=self._sum_error_summary(source_error_summary),
                    error_summary=source_error_summary,
                    last_indexed_at=now_iso,
                    sync_warnings=source_sync_warnings,
                )
            except sqlite3.Error as exc:
                source_last_status = "parse_error"
                source_error_summary = self._increment_error_summary(
                    source_error_summary, "other_errors"
                )
                source_error_diagnostics.append(
                    {
                        "source_id": authorization.source_id,
                        "path": str(authorization.path),
                        "reason": f"index_write_error: {type(exc).__name__}: {exc}",
                    }
                )
                self._persist_source_status(
                    authorization=authorization,
                    now_iso=now_iso,
                    source_last_status=source_last_status,
                    source_drift_detected=source_drift_detected,
                    source_parser_mode="failed",
                    source_error_summary=source_error_summary,
                    statuses_by_id=existing_statuses_by_id,
                    ignored_files_due_to_policy_restriction=ignored_files_due_to_policy_restriction,
                    sync_warnings=source_sync_warnings,
                )
                continue
            counts["documents"] += len(documents_tuple)
            counts["chunks"] += replaced_chunks
            self._persist_source_status(
                authorization=authorization,
                now_iso=now_iso,
                source_last_status=source_last_status,
                source_drift_detected=source_drift_detected,
                source_parser_mode=source_parser_mode,
                source_error_summary=source_error_summary,
                statuses_by_id=existing_statuses_by_id,
                ignored_files_due_to_policy_restriction=ignored_files_due_to_policy_restriction,
                sync_warnings=source_sync_warnings,
            )
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

    def _empty_error_summary(self) -> dict[str, int]:
        return {"parse_errors": 0, "schema_drift": 0, "policy_drift": 0, "other_errors": 0}

    def _increment_error_summary(self, summary: dict[str, int], key: str) -> dict[str, int]:
        summary[key] = summary.get(key, 0) + 1
        return summary

    def _merge_error_summary(
        self, base: dict[str, int], added: dict[str, int]
    ) -> dict[str, int]:
        merged = dict(base)
        for key, value in added.items():
            merged[key] = merged.get(key, 0) + value
        return merged

    def _sum_error_summary(self, summary: dict[str, int]) -> int:
        return sum(summary.values())

    def _persist_source_status(
        self,
        *,
        authorization: SourceAuthorization,
        now_iso: str,
        source_last_status: str,
        source_drift_detected: bool,
        source_parser_mode: str,
        source_error_summary: dict[str, int],
        statuses_by_id: dict[str, SourceIndexStatus],
        ignored_files_due_to_policy_restriction: int,
        sync_warnings: list[str] | None = None,
    ) -> None:
        existing_status = statuses_by_id.get(authorization.source_id)
        prior_summary = (
            existing_status.error_summary if existing_status is not None else {}
        )
        prior_count = existing_status.error_count if existing_status is not None else 0
        merged_summary = self._merge_error_summary(prior_summary, source_error_summary)
        self.index.update_source_status(
            authorization,
            last_index_status=source_last_status,
            drift_detected=source_drift_detected,
            parser_mode=source_parser_mode,
            ignored_files_due_to_policy_restriction=(
                ignored_files_due_to_policy_restriction
            ),
            error_count=prior_count + self._sum_error_summary(source_error_summary),
            error_summary=merged_summary,
            sync_warnings=sync_warnings,
            last_indexed_at=now_iso,
        )

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
                parser_mode = _normalize_parser_mode(status.parser_mode)
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
                    "parser_mode_label": _parser_mode_label(parser_mode),
                    "parser_mode_chunking_tooltip": _parser_mode_chunking_tooltip(parser_mode),
                    "drift_detected": drift_detected,
                    "ignored_files_due_to_policy_restriction": ignored_files_due_to_policy_restriction,
                    "error_count": status.error_count if status else 0,
                    "error_summary": status.error_summary if status else {},
                    "sync_warnings": status.sync_warnings if status else [],
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
        sync_warning_count = 0
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
            if status.sync_warnings:
                sync_warning_count += len(status.sync_warnings)
                issues.append(
                    {
                        "source_id": source.source_id,
                        "reason": "sync_warning",
                        "warnings": "; ".join(status.sync_warnings),
                    }
                )
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
            if _normalize_parser_mode(status.parser_mode) == "fallback_text":
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
            "sync_warning_count": sync_warning_count,
        }

    def search(self, query: str, *, limit: int = 10) -> tuple[SearchResult, ...]:
        return self.index.search(query, limit=limit)

    def privacy_audit(self, *, fix_permissions: bool = False) -> dict[str, Any]:
        return self._collect_privacy_audit(fix_permissions=fix_permissions)

    def debug_report(self) -> dict[str, Any]:
        privacy_audit = self._collect_privacy_audit()
        status_payload = self.status()
        source_status_rows = []
        total_error_summary: dict[str, int] = self._empty_error_summary()
        for item in status_payload["sources"]:
            summary = item.get("error_summary", {})
            source_row_error_summary = self._merge_error_summary(self._empty_error_summary(), summary)
            source_status_rows.append(
                {
                    "source_id": item["source_id"],
                    "source_type": item["source_type"],
                    "status": item["status"],
                    "last_indexed_at": item["last_indexed_at"],
                    "parser_mode": item["parser_mode"],
                    "drift_detected": item["drift_detected"],
                    "ignored_files_due_to_policy_restriction": item["ignored_files_due_to_policy_restriction"],
                    "sync_warnings": item["sync_warnings"],
                    "error_summary": source_row_error_summary,
                    "error_count": item["error_count"],
                }
            )
            total_error_summary = self._merge_error_summary(
                total_error_summary,
                source_row_error_summary,
            )
        indexed_counts = self.index.indexed_counts()
        return {
            "generated_at": _now_utc_iso(),
            "workspace": str(self.workspace_root),
            "configuration_overview": {
                "sources_discovered": len(status_payload["sources"]),
                "sources_authorized": len(
                    [
                        source
                        for source in self.authorization_store.authorized_sources()
                    ]
                ),
                "index_sources": indexed_counts["sources"],
                "documents": indexed_counts["documents"],
                "chunks": indexed_counts["chunks"],
            },
            "error_counts": {
                "total": sum(total_error_summary.values()),
                "by_type": total_error_summary,
            },
            "source_status_summary": source_status_rows,
            "privacy_posture": {
                "ok": privacy_audit["ok"],
                "failed_checks": [
                    {key: item[key] for key in ("id", "ok") if key in item}
                    for item in privacy_audit["checks"]
                ],
            },
            "warnings": len(privacy_audit["warnings"]),
            "recommendation": (
                "Share this report in a GitHub issue/discussion after removing "
                "any local paths you want to keep private."
            ),
        }

    def _collect_privacy_audit(self, *, fix_permissions: bool = False) -> dict[str, Any]:
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


def _normalize_parser_mode(parser_mode: str | None) -> str:
    return "fallback_text" if parser_mode == "raw_text" else (parser_mode or "unknown")


def _parser_mode_label(parser_mode: str) -> str:
    if parser_mode == "fallback_text":
        return "Raw Text Source"
    if parser_mode == "failed":
        return "Failed to Parse"
    return "Structured Chat"


def _parser_mode_chunking_tooltip(parser_mode: str) -> str:
    if parser_mode == "fallback_text":
        return (
            "Text chunks use 4000-character windows with 250-character overlap to preserve "
            "adjacent context."
        )
    return "Structured parser preserves message boundaries and metadata."
