from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from dataclasses import replace
import subprocess
import sys
import zipfile

import pytest
import anamnesis.service as service_module
from anamnesis.index import AnamnesisIndex
from anamnesis.models import Exchange, SessionDocument, SourceAuthorization
from anamnesis.parser_common import MAX_TEXT_CHUNK_CHARS
from anamnesis.service import AnamnesisService
from anamnesis.registry import (
    SOURCE_CAPABILITY_BACKLOG,
    SOURCE_CAPABILITY_REGISTRY,
    backlog_by_source_type,
    definition_for_source_type,
)


def _mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


def _check_by_id(audit: dict, check_id: str, *, path: Path | None = None) -> dict:
    matches = [
        check
        for check in audit["checks"]
        if check["id"] == check_id and (path is None or check["path"] == str(path))
    ]
    assert matches
    return matches[0]


def test_reindex_purges_deleted_source_files(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source_root = home / ".codex" / "sessions"
    source_root.mkdir(parents=True)
    session_path = source_root / "session.json"
    deleted_tokens = ("vanishingtoken", "zzzremnant", "markerword")
    session_path.write_text(
        json.dumps(
            {
                "id": "deleted-session",
                "messages": [
                    {
                        "role": "user",
                        "content": " ".join(deleted_tokens),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    service = AnamnesisService(workspace_root=tmp_path / "workspace", home=home)
    codex = next(source for source in service.discover() if source.source_type == "codex")
    service.authorize(codex.source_id)

    assert service.index_authorized_sources() == {"chunks": 1, "documents": 1, "sources": 1}
    database_path = tmp_path / "workspace" / "anamnesis.sqlite"
    with sqlite3.connect(tmp_path / "workspace" / "anamnesis.sqlite") as connection:
        assert connection.execute(
            "SELECT source_id, source_type, display_name, path FROM sources"
        ).fetchall() == [(codex.source_id, "codex", "Codex", str(source_root))]
    assert len(service.search("vanishingtoken zzzremnant markerword")) == 1
    raw_before = database_path.read_bytes()
    for token in deleted_tokens:
        assert token.encode("utf-8") in raw_before

    session_path.unlink()

    assert service.index_authorized_sources() == {"chunks": 0, "documents": 0, "sources": 1}
    assert service.search("vanishingtoken zzzremnant markerword") == ()
    raw_after = database_path.read_bytes()
    for token in deleted_tokens:
        assert token.encode("utf-8") not in raw_after


def test_reindex_keeps_old_active_index_on_unexpected_parse_failure(
    tmp_path: Path, monkeypatch
) -> None:
    home = tmp_path / "home"
    source_root = home / ".codex" / "sessions"
    source_root.mkdir(parents=True)
    session_path = source_root / "session.json"
    session_path.write_text(
        json.dumps(
            {
                "id": "stable-session",
                "messages": [{"role": "user", "content": "old durable content"}],
            }
        ),
        encoding="utf-8",
    )

    service = AnamnesisService(workspace_root=tmp_path / "workspace", home=home)
    codex = next(source for source in service.discover() if source.source_type == "codex")
    service.authorize(codex.source_id)
    assert service.index_authorized_sources() == {"chunks": 1, "documents": 1, "sources": 1}

    session_path.write_text(
        json.dumps(
            {
                "id": "stable-session",
                "messages": [{"role": "user", "content": "new fragile content"}],
            }
        ),
        encoding="utf-8",
    )

    def fail_parse(*args, **kwargs):
        raise RuntimeError("parser exploded")

    monkeypatch.setattr(service_module, "parse_session_file", fail_parse)

    assert service.index_authorized_sources() == {
        "chunks": 0,
        "documents": 0,
        "source_error_diagnostics": [
            {
                "path": str(session_path),
                "reason": "unexpected_parse_error: RuntimeError",
                "source_id": codex.source_id,
            }
        ],
        "source_errors": 1,
        "sources": 1,
    }
    assert len(service.search("old durable content")) == 1
    assert service.search("new fragile content") == ()


def test_replace_source_documents_rolls_back_on_insert_failure(
    tmp_path: Path, monkeypatch
) -> None:
    index = AnamnesisIndex(tmp_path / "workspace" / "anamnesis.sqlite")
    source = SourceAuthorization(
        source_id="codex:test-source",
        source_type="codex",
        display_name="Codex",
        path=tmp_path / "home" / ".codex" / "sessions",
        authorized=True,
    )
    old_document = SessionDocument(
        source_id=source.source_id,
        source_type=source.source_type,
        session_id="rollback-session",
        path=source.path / "session.json",
        title="Rollback Session",
        created_at=None,
        modified_at=None,
        exchanges=(Exchange(role="user", text="old rollback durable"),),
        metadata={},
    )
    new_document = SessionDocument(
        source_id=source.source_id,
        source_type=source.source_type,
        session_id="rollback-session",
        path=source.path / "session.json",
        title="Rollback Session",
        created_at=None,
        modified_at=None,
        exchanges=(Exchange(role="user", text="new rollback fragile"),),
        metadata={},
    )

    assert index.replace_source_documents(source, (old_document,)) == 1

    def fail_insert(connection, document):
        raise sqlite3.OperationalError("simulated insert failure")

    monkeypatch.setattr(index, "_insert_document", fail_insert)

    with pytest.raises(sqlite3.OperationalError, match="simulated insert failure"):
        index.replace_source_documents(source, (new_document,))

    assert len(index.search("old rollback durable")) == 1
    assert index.search("new rollback fragile") == ()


def test_compact_source_replacement_vacuums_deleted_tokens_for_direct_callers(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "workspace" / "anamnesis.sqlite"
    index = AnamnesisIndex(database_path)
    source = SourceAuthorization(
        source_id="codex:compact-source",
        source_type="codex",
        display_name="Codex",
        path=tmp_path / "home" / ".codex" / "sessions",
        authorized=True,
    )
    old_tokens = ("compactold", "compactghost", "compactremnant")
    old_document = SessionDocument(
        source_id=source.source_id,
        source_type=source.source_type,
        session_id="compact-session",
        path=source.path / "session.json",
        title="Compact Session",
        created_at=None,
        modified_at=None,
        exchanges=(Exchange(role="user", text=" ".join(old_tokens)),),
        metadata={},
    )
    new_document = SessionDocument(
        source_id=source.source_id,
        source_type=source.source_type,
        session_id="compact-session",
        path=source.path / "session.json",
        title="Compact Session",
        created_at=None,
        modified_at=None,
        exchanges=(Exchange(role="user", text="compactfresh token"),),
        metadata={},
    )

    assert index.replace_source_documents(source, (old_document,), compact=True) == 1
    raw_before = database_path.read_bytes()
    for token in old_tokens:
        assert token.encode("utf-8") in raw_before

    assert index.replace_source_documents(source, (new_document,), compact=True) == 1

    assert index.search("compactfresh token")[0].session_id == "compact-session"
    assert index.search("compactold compactghost compactremnant") == ()
    raw_after = database_path.read_bytes()
    for token in old_tokens:
        assert token.encode("utf-8") not in raw_after


def test_index_reports_sqlite_write_error_without_aborting_run(
    tmp_path: Path, monkeypatch
) -> None:
    home = tmp_path / "home"
    codex_root = home / ".codex" / "sessions"
    manual_root = home / "Anamnesis" / "imports"
    codex_root.mkdir(parents=True)
    manual_root.mkdir(parents=True)
    codex_path = codex_root / "session.json"
    manual_path = manual_root / "manual.json"
    codex_path.write_text(
        json.dumps(
            {
                "id": "codex-write-failure",
                "messages": [{"role": "user", "content": "old write durable"}],
            }
        ),
        encoding="utf-8",
    )
    manual_path.write_text(
        json.dumps(
            {
                "id": "manual-write-success",
                "messages": [{"role": "user", "content": "manual before refresh"}],
            }
        ),
        encoding="utf-8",
    )

    service = AnamnesisService(workspace_root=tmp_path / "workspace", home=home)
    sources = {source.source_type: source for source in service.discover()}
    codex = sources["codex"]
    manual = sources["manual_import"]
    service.authorize(codex.source_id)
    service.authorize(manual.source_id)
    assert service.index_authorized_sources() == {"chunks": 2, "documents": 2, "sources": 2}

    codex_path.write_text(
        json.dumps(
            {
                "id": "codex-write-failure",
                "messages": [{"role": "user", "content": "new write fragile"}],
            }
        ),
        encoding="utf-8",
    )
    manual_path.write_text(
        json.dumps(
            {
                "id": "manual-write-success",
                "messages": [{"role": "user", "content": "manual after refresh"}],
            }
        ),
        encoding="utf-8",
    )

    original_insert = service.index._insert_document

    def fail_codex_insert(connection, document):
        if document.source_id == codex.source_id:
            raise sqlite3.OperationalError("simulated write failure")
        return original_insert(connection, document)

    monkeypatch.setattr(service.index, "_insert_document", fail_codex_insert)

    assert service.index_authorized_sources() == {
        "chunks": 1,
        "documents": 1,
        "source_error_diagnostics": [
            {
                "path": str(codex.path),
                "reason": "index_write_error: OperationalError: simulated write failure",
                "source_id": codex.source_id,
            }
        ],
        "source_errors": 1,
        "sources": 2,
    }
    assert len(service.search("old write durable")) == 1
    assert service.search("new write fragile") == ()
    assert len(service.search("manual after refresh")) == 1
    assert service.search("manual before refresh") == ()


def test_index_run_vacuums_once(
    tmp_path: Path, monkeypatch
) -> None:
    home = tmp_path / "home"
    codex_root = home / ".codex" / "sessions"
    manual_root = home / "Anamnesis" / "imports"
    codex_root.mkdir(parents=True)
    manual_root.mkdir(parents=True)
    (codex_root / "session.json").write_text(
        json.dumps(
            {
                "id": "codex-vacuum-once",
                "messages": [{"role": "user", "content": "codex vacuum content"}],
            }
        ),
        encoding="utf-8",
    )
    (manual_root / "manual.json").write_text(
        json.dumps(
            {
                "id": "manual-vacuum-once",
                "messages": [{"role": "user", "content": "manual vacuum content"}],
            }
        ),
        encoding="utf-8",
    )

    service = AnamnesisService(workspace_root=tmp_path / "workspace", home=home)
    sources = {source.source_type: source for source in service.discover()}
    service.authorize(sources["codex"].source_id)
    service.authorize(sources["manual_import"].source_id)

    vacuum_calls = 0
    original_vacuum = service.index._vacuum

    def count_vacuum():
        nonlocal vacuum_calls
        vacuum_calls += 1
        original_vacuum()

    monkeypatch.setattr(service.index, "_vacuum", count_vacuum)

    assert service.index_authorized_sources() == {"chunks": 2, "documents": 2, "sources": 2}
    assert vacuum_calls == 1

    service.revoke(sources["codex"].source_id)
    assert vacuum_calls == 2


def test_workspace_database_and_authorization_files_are_private(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    source_root = home / ".codex" / "sessions"
    source_root.mkdir(parents=True)
    (source_root / "session.json").write_text(
        json.dumps(
            {
                "id": "private-mode-session",
                "messages": [{"role": "user", "content": "private mode content"}],
            }
        ),
        encoding="utf-8",
    )

    old_umask = os.umask(0)
    try:
        workspace = tmp_path / "workspace"
        service = AnamnesisService(workspace_root=workspace, home=home)
        codex = next(source for source in service.discover() if source.source_type == "codex")
        service.authorize(codex.source_id)
        service.index_authorized_sources()
    finally:
        os.umask(old_umask)

    assert _mode(workspace) == 0o700
    assert _mode(workspace / "sources.authorization.json") == 0o600
    assert _mode(workspace / "anamnesis.sqlite") == 0o600


def test_privacy_audit_passes_on_fresh_private_workspace(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source_root = home / ".codex" / "sessions"
    source_root.mkdir(parents=True)
    (source_root / "session.json").write_text(
        json.dumps(
            {
                "id": "privacy-audit-session",
                "messages": [{"role": "user", "content": "audit private content"}],
            }
        ),
        encoding="utf-8",
    )

    workspace = tmp_path / "workspace"
    service = AnamnesisService(workspace_root=workspace, home=home)
    codex = next(source for source in service.discover() if source.source_type == "codex")
    service.authorize(codex.source_id)
    service.index_authorized_sources()

    audit = service.privacy_audit()

    assert audit["ok"] is True
    assert audit["fixed"] == []
    assert _check_by_id(audit, "workspace_mode")["actual_mode"] == "700"
    assert _check_by_id(audit, "authorization_file_mode")["actual_mode"] == "600"
    assert _check_by_id(audit, "database_file_mode")["actual_mode"] == "600"
    assert _check_by_id(audit, "sqlite_secure_delete")["actual"] == "1"
    assert any(warning["id"] == "plaintext_sqlite" for warning in audit["warnings"])


def test_privacy_audit_reports_and_fixes_legacy_permissive_modes(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    source_root = home / ".codex" / "sessions"
    source_root.mkdir(parents=True)
    (source_root / "session.json").write_text(
        json.dumps(
            {
                "id": "legacy-mode-session",
                "messages": [{"role": "user", "content": "legacy mode content"}],
            }
        ),
        encoding="utf-8",
    )

    workspace = tmp_path / "workspace"
    service = AnamnesisService(workspace_root=workspace, home=home)
    codex = next(source for source in service.discover() if source.source_type == "codex")
    service.authorize(codex.source_id)
    service.index_authorized_sources()

    authorization_path = workspace / "sources.authorization.json"
    database_path = workspace / "anamnesis.sqlite"
    workspace.chmod(0o755)
    authorization_path.chmod(0o644)
    database_path.chmod(0o644)

    audit = service.privacy_audit()

    assert audit["ok"] is False
    assert _check_by_id(audit, "workspace_mode")["actual_mode"] == "755"
    assert _check_by_id(audit, "authorization_file_mode")["actual_mode"] == "644"
    assert _check_by_id(audit, "database_file_mode")["actual_mode"] == "644"
    assert _mode(workspace) == 0o755
    assert _mode(authorization_path) == 0o644
    assert _mode(database_path) == 0o644

    fixed_audit = service.privacy_audit(fix_permissions=True)

    assert fixed_audit["ok"] is True
    assert {
        (item["id"], item["path"], item["mode"]) for item in fixed_audit["fixed"]
    } == {
        ("workspace_mode", str(workspace), "700"),
        ("authorization_file_mode", str(authorization_path), "600"),
        ("database_file_mode", str(database_path), "600"),
    }
    assert _mode(workspace) == 0o700
    assert _mode(authorization_path) == 0o600
    assert _mode(database_path) == 0o600


def test_privacy_audit_reports_and_fixes_sqlite_sidecars(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    database_path = workspace / "anamnesis.sqlite"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE marker (id INTEGER PRIMARY KEY)")
    sidecars = [
        Path(f"{database_path}-wal"),
        Path(f"{database_path}-shm"),
        Path(f"{database_path}-journal"),
    ]
    for sidecar in sidecars:
        sidecar.write_text("sidecar", encoding="utf-8")
        sidecar.chmod(0o644)

    service = AnamnesisService(workspace_root=workspace, home=tmp_path / "home")
    audit = service.privacy_audit()

    assert audit["ok"] is False
    for sidecar in sidecars:
        check = _check_by_id(audit, "sqlite_sidecar_mode", path=sidecar)
        assert check["actual_mode"] == "644"

    fixed_audit = service.privacy_audit(fix_permissions=True)

    assert fixed_audit["ok"] is True
    assert {
        (item["id"], item["path"], item["mode"])
        for item in fixed_audit["fixed"]
        if item["id"] == "sqlite_sidecar_mode"
    } == {("sqlite_sidecar_mode", str(sidecar), "600") for sidecar in sidecars}
    for sidecar in sidecars:
        assert _mode(sidecar) == 0o600


def test_privacy_audit_reports_missing_sqlcipher_dependency_when_encryption_is_enabled(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    manifest_path = workspace / "database-encryption.json"
    manifest_path.write_text(
        json.dumps(
            {
                "enabled": True,
                "provider": "password",
                "key_salt": "c2Vjb25kX3NhbHQ=",
                "key_iterations": 120000,
                "keyring_service": "anamnesis",
                "keyring_key_name": "index-encryption-secret",
                "created_at": "2026-06-04T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(service_module, "supports_sqlcipher", lambda: False)
    service = AnamnesisService(workspace_root=workspace, home=tmp_path / "home")
    audit = service.privacy_audit()

    sqlcipher_check = _check_by_id(audit, "database_encryption_sqlcipher_dependency")
    assert sqlcipher_check["ok"] is False
    assert any(
        item["id"] == "database_encryption_dependency_missing"
        for item in audit["warnings"]
    )


def test_privacy_audit_reports_invalid_encrypted_db_key_verification(
    tmp_path: Path,
    monkeypatch,
) -> None:
    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    database_path = workspace / "anamnesis.sqlite"
    manifest_path = workspace / "database-encryption.json"
    manifest_path.write_text(
        json.dumps(
            {
                "enabled": True,
                "provider": "password",
                "key_salt": "dGVzdF9zYWx0",
                "key_iterations": 120000,
                "keyring_service": "anamnesis",
                "keyring_key_name": "index-encryption-secret",
                "created_at": "2026-06-04T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE marker (id INTEGER PRIMARY KEY)")

    monkeypatch.setattr(service_module, "supports_sqlcipher", lambda: True)
    monkeypatch.setattr(
        service_module,
        "probe_sqlcipher_connection",
        lambda *_args, **_kwargs: False,
    )

    service = AnamnesisService(workspace_root=workspace, home=home)
    service.set_database_password("test-password")
    audit = service.privacy_audit()

    key_check = _check_by_id(audit, "database_encryption_key")
    assert key_check["ok"] is False
    assert key_check["actual"] == "invalid"
    assert any(
        item["id"] == "database_encryption_verification_failed"
        for item in audit["warnings"]
    )


def test_privacy_audit_cli_outputs_json_without_creating_workspace(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "missing-workspace"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "anamnesis",
            "--workspace",
            str(workspace),
            "privacy-audit",
        ],
        capture_output=True,
        cwd=Path(__file__).resolve().parents[2],
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    assert payload["fixed"] == []
    assert payload["warnings"] == []
    assert _check_by_id(payload, "workspace_mode")["present"] is False
    assert not workspace.exists()
    assert completed.stderr == ""


def test_revoke_vacuums_plaintext_out_of_sqlite_file(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source_root = home / ".codex" / "sessions"
    source_root.mkdir(parents=True)
    tokens = ("ultraunique", "remnants", "xyzzy")
    (source_root / "session.json").write_text(
        json.dumps(
            {
                "id": "secret-session",
                "messages": [
                    {"role": "user", "content": " ".join(tokens)},
                ],
            }
        ),
        encoding="utf-8",
    )

    workspace = tmp_path / "workspace"
    database_path = workspace / "anamnesis.sqlite"
    service = AnamnesisService(workspace_root=workspace, home=home)
    codex = next(source for source in service.discover() if source.source_type == "codex")
    service.authorize(codex.source_id)

    assert service.index_authorized_sources() == {"chunks": 1, "documents": 1, "sources": 1}
    raw_before = database_path.read_bytes()
    for token in tokens:
        assert token.encode("utf-8") in raw_before

    assert service.revoke(codex.source_id) == 1
    assert service.search("ultraunique") == ()
    raw_after = database_path.read_bytes()
    for token in tokens:
        assert token.encode("utf-8") not in raw_after


def test_source_policy_snapshot_blocks_registry_drift(
    tmp_path: Path, monkeypatch
) -> None:
    home = tmp_path / "home"
    source_root = home / ".codex" / "sessions"
    source_root.mkdir(parents=True)
    (source_root / "session.json").write_text(
        json.dumps(
            {
                "id": "snapshot-session",
                "messages": [
                    {"role": "user", "content": "policy snapshot content"},
                ],
            }
        ),
        encoding="utf-8",
    )

    workspace = tmp_path / "workspace"
    service = AnamnesisService(workspace_root=workspace, home=home)
    codex = next(source for source in service.discover() if source.source_type == "codex")
    service.authorize(codex.source_id)

    manifest = json.loads((workspace / "sources.authorization.json").read_text())
    assert manifest["sources"][0]["definition_id"] == codex.definition_id

    codex_definition = definition_for_source_type("codex")
    assert codex_definition is not None
    drifted_definition = replace(
        codex_definition,
        file_suffixes=(".md",),
        definition_id="",
    )
    monkeypatch.setattr(
        service_module,
        "definitions_by_definition_id",
        lambda: {drifted_definition.definition_id: drifted_definition},
    )

    assert service.index_authorized_sources() == {
        "chunks": 0,
        "documents": 0,
        "source_error_diagnostics": [
            {
                "path": str(codex.path),
                "reason": f"source_policy_drift: unknown_definition_id={codex.definition_id}",
                "source_id": codex.source_id,
            }
        ],
        "source_errors": 1,
        "sources": 1,
    }
    assert service.search("policy snapshot content") == ()


def test_legacy_authorization_without_definition_id_still_indexes(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    source_root = home / ".codex" / "sessions"
    source_root.mkdir(parents=True)
    session_path = source_root / "session.json"
    session_path.write_text(
        json.dumps(
            {
                "id": "legacy-auth-session",
                "messages": [{"role": "user", "content": "legacy authorization content"}],
            }
        ),
        encoding="utf-8",
    )

    workspace = tmp_path / "workspace"
    discovery_service = AnamnesisService(workspace_root=workspace, home=home)
    codex = next(
        source for source in discovery_service.discover() if source.source_type == "codex"
    )
    workspace.mkdir(parents=True)
    (workspace / "sources.authorization.json").write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "source_id": codex.source_id,
                        "source_type": "codex",
                        "display_name": "Codex",
                        "path": str(source_root),
                        "authorized": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    service = AnamnesisService(workspace_root=workspace, home=home)

    assert service.index_authorized_sources() == {"chunks": 1, "documents": 1, "sources": 1}
    assert service.search("legacy authorization content")[0].session_id == (
        "legacy-auth-session"
    )


def test_registry_definition_ids_are_unique_and_present() -> None:
    definitions = (*SOURCE_CAPABILITY_REGISTRY, *SOURCE_CAPABILITY_BACKLOG)
    definition_ids = [definition.definition_id for definition in definitions]

    assert all(definition_ids)
    assert len(definition_ids) == len(set(definition_ids))


def test_chatgpt_export_does_not_scan_downloads(tmp_path: Path) -> None:
    home = tmp_path / "home"
    downloads = home / "Downloads"
    downloads.mkdir(parents=True)
    (downloads / "conversations.json").write_text(
        json.dumps(
            [
                {
                    "id": "downloads-chat",
                    "messages": [{"role": "user", "content": "downloads secret"}],
                }
            ]
        ),
        encoding="utf-8",
    )

    export_root = home / "Anamnesis" / "chatgpt_exports"
    export_root.mkdir(parents=True)
    (export_root / "conversations.json").write_text(
        json.dumps(
            [
                {
                    "id": "chatgpt-export",
                    "messages": [{"role": "user", "content": "dedicated export"}],
                }
            ]
        ),
        encoding="utf-8",
    )

    service = AnamnesisService(workspace_root=tmp_path / "workspace", home=home)
    chatgpt = next(
        source for source in service.discover() if source.source_type == "chatgpt_export"
    )

    assert chatgpt.path == export_root
    assert chatgpt.file_count == 1

    service.authorize(chatgpt.source_id)
    assert service.index_authorized_sources() == {"chunks": 1, "documents": 1, "sources": 1}
    assert len(service.search("dedicated export")) == 1
    assert service.search("downloads secret") == ()


def test_chatgpt_export_ignores_non_conversation_json_files(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    export_root = home / "Anamnesis" / "chatgpt_exports"
    export_root.mkdir(parents=True)
    (export_root / "conversations.json").write_text(
        json.dumps(
            [
                {
                    "id": "chatgpt-allowed",
                    "messages": [{"role": "user", "content": "allowed export content"}],
                }
            ]
        ),
        encoding="utf-8",
    )
    (export_root / "unrelated.json").write_text(
        json.dumps(
            {
                "id": "chatgpt-unrelated",
                "messages": [{"role": "user", "content": "unrelated export secret"}],
            }
        ),
        encoding="utf-8",
    )

    service = AnamnesisService(workspace_root=tmp_path / "workspace", home=home)
    chatgpt = next(
        source for source in service.discover() if source.source_type == "chatgpt_export"
    )

    assert chatgpt.file_count == 1

    service.authorize(chatgpt.source_id)
    assert service.index_authorized_sources() == {"chunks": 1, "documents": 1, "sources": 1}
    assert len(service.search("allowed export content")) == 1
    assert service.search("unrelated export secret") == ()


def test_chatgpt_zip_indexes_only_conversations_member(tmp_path: Path) -> None:
    home = tmp_path / "home"
    export_root = home / "Anamnesis" / "chatgpt_exports"
    export_root.mkdir(parents=True)
    zip_path = export_root / "chatgpt-export.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr(
            "conversations.json",
            json.dumps(
                [
                    {
                        "id": "zip-allowed",
                        "messages": [{"role": "user", "content": "zip allowed content"}],
                    }
                ]
            ),
        )
        archive.writestr(
            "account/unrelated.json",
            json.dumps(
                {
                    "id": "zip-unrelated",
                    "messages": [{"role": "user", "content": "zip unrelated secret"}],
                }
            ),
        )

    service = AnamnesisService(workspace_root=tmp_path / "workspace", home=home)
    chatgpt = next(
        source for source in service.discover() if source.source_type == "chatgpt_export"
    )
    service.authorize(chatgpt.source_id)

    assert service.index_authorized_sources() == {"chunks": 1, "documents": 1, "sources": 1}
    assert len(service.search("zip allowed content")) == 1
    assert service.search("zip unrelated secret") == ()


def test_chatgpt_mapping_export_orders_parent_child_messages(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    export_root = home / "Anamnesis" / "chatgpt_exports"
    export_root.mkdir(parents=True)
    (export_root / "conversations.json").write_text(
        json.dumps(
            [
                {
                    "id": "mapping-chat",
                    "title": "Mapping Chat",
                    "mapping": {
                        "root": {
                            "id": "root",
                            "parent": None,
                            "children": ["first"],
                            "message": None,
                        },
                        "second": {
                            "id": "second",
                            "parent": "first",
                            "children": [],
                            "message": {
                                "author": {"role": "assistant"},
                                "content": {"parts": ["second mapping text"]},
                            },
                        },
                        "first": {
                            "id": "first",
                            "parent": "root",
                            "children": ["second"],
                            "message": {
                                "author": {"role": "user"},
                                "content": {"parts": ["first mapping text"]},
                            },
                        },
                    },
                }
            ]
        ),
        encoding="utf-8",
    )

    workspace = tmp_path / "workspace"
    service = AnamnesisService(workspace_root=workspace, home=home)
    chatgpt = next(
        source for source in service.discover() if source.source_type == "chatgpt_export"
    )
    service.authorize(chatgpt.source_id)

    assert service.index_authorized_sources() == {"chunks": 2, "documents": 1, "sources": 1}
    with sqlite3.connect(workspace / "anamnesis.sqlite") as connection:
        rows = connection.execute(
            "SELECT role, text FROM chunks ORDER BY chunk_id"
        ).fetchall()

    assert rows == [
        ("user", "first mapping text"),
        ("assistant", "second mapping text"),
    ]


def test_cloud_exports_use_manual_import_roots_not_home_history_paths(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    legacy_claude = home / ".claude" / "sessions"
    legacy_claude.mkdir(parents=True)
    (legacy_claude / "session.json").write_text(
        json.dumps(
            {
                "id": "legacy-claude-cloud",
                "messages": [{"role": "user", "content": "legacy cloud secret"}],
            }
        ),
        encoding="utf-8",
    )
    claude_import = home / "Anamnesis" / "imports" / "claude"
    claude_import.mkdir(parents=True)

    service = AnamnesisService(workspace_root=tmp_path / "workspace", home=home)
    cloud_sources = {
        source.source_type: source
        for source in service.discover()
        if source.source_type
        in {
            "claude",
            "chatgpt_export",
            "gemini_export",
            "character_ai_export",
            "notion_export",
        }
    }

    assert cloud_sources["claude"].path == claude_import
    assert cloud_sources["claude"].default_discovery_policy == "manual_import_only"
    assert cloud_sources["claude"].access_method == "user_supplied_export"
    assert cloud_sources["claude"].file_count == 0
    assert cloud_sources["chatgpt_export"].default_discovery_policy == "manual_import_only"
    assert cloud_sources["gemini_export"].default_discovery_policy == "manual_import_only"
    assert cloud_sources["character_ai_export"].default_discovery_policy == "manual_import_only"
    assert cloud_sources["notion_export"].default_discovery_policy == "manual_import_only"


def test_antigravity_raw_path_is_backlog_not_active_discovery(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    antigravity_raw = home / ".gemini" / "antigravity" / "conversations"
    antigravity_raw.mkdir(parents=True)
    (antigravity_raw / "session.json").write_text(
        json.dumps(
            {
                "id": "antigravity-raw",
                "messages": [{"role": "user", "content": "antigravity raw secret"}],
            }
        ),
        encoding="utf-8",
    )

    service = AnamnesisService(workspace_root=tmp_path / "workspace", home=home)
    active_sources = {source.source_type for source in service.discover()}
    backlog_sources = backlog_by_source_type()

    assert "gemini_antigravity" not in active_sources
    assert (
        backlog_sources["gemini_antigravity"].default_discovery_policy
        == "docs_backlog_only"
    )
    assert service.index_authorized_sources() == {
        "chunks": 0,
        "documents": 0,
        "sources": 0,
    }
    assert service.search("antigravity raw secret") == ()


def test_second_matrix_sources_are_backlog_only(tmp_path: Path) -> None:
    service = AnamnesisService(
        workspace_root=tmp_path / "workspace",
        home=tmp_path / "home",
    )
    active_sources = {source.source_type for source in service.discover()}
    backlog_sources = backlog_by_source_type()
    expected_backlog = {
        "anythingllm",
        "deepseek_chat",
        "lindy",
        "meta_ai",
        "mistral_le_chat",
        "perplexity",
    }

    assert active_sources.isdisjoint(expected_backlog)
    assert expected_backlog <= set(backlog_sources)
    for source_type in expected_backlog - {"anythingllm", "lindy"}:
        assert (
            backlog_sources[source_type].default_discovery_policy
            == "docs_backlog_only"
        )
    assert (
        backlog_sources["anythingllm"].default_discovery_policy
        == "manual_import_only"
    )
    assert backlog_sources["lindy"].default_discovery_policy == "manual_import_only"


def test_encrypted_chatgpt_zip_is_skipped_with_diagnostics(
    tmp_path: Path, monkeypatch
) -> None:
    home = tmp_path / "home"
    export_root = home / "Anamnesis" / "chatgpt_exports"
    export_root.mkdir(parents=True)
    zip_path = export_root / "encrypted-chatgpt.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr(
            "conversations.json",
            json.dumps(
                [
                    {
                        "id": "encrypted-chat",
                        "messages": [{"role": "user", "content": "encrypted secret"}],
                    }
                ]
            ),
        )

    original_read = zipfile.ZipFile.read

    def encrypted_read(self, name, pwd=None):
        if Path(name).name == "conversations.json":
            raise RuntimeError(
                "File 'conversations.json' is encrypted, password required for extraction"
            )
        return original_read(self, name, pwd=pwd)

    monkeypatch.setattr(zipfile.ZipFile, "read", encrypted_read)

    service = AnamnesisService(workspace_root=tmp_path / "workspace", home=home)
    chatgpt = next(
        source for source in service.discover() if source.source_type == "chatgpt_export"
    )

    assert chatgpt.file_count == 1

    service.authorize(chatgpt.source_id)
    assert service.index_authorized_sources() == {
        "chunks": 0,
        "documents": 0,
        "skipped_file_diagnostics": [
            {
                "path": str(zip_path),
                "reason": (
                    "zip_error: File 'conversations.json' is encrypted, "
                    "password required for extraction"
                ),
            }
        ],
        "skipped_files": 1,
        "sources": 1,
    }
    assert service.search("encrypted secret") == ()


def test_indexing_processes_source_files_incrementally(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source_root = home / ".codex" / "sessions"
    source_root.mkdir(parents=True)
    for index in range(3):
        (source_root / f"session-{index}.json").write_text(
            json.dumps(
                {
                    "id": f"session-{index}",
                    "messages": [
                        {
                            "role": "user",
                            "content": f"incremental unique {index}",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    service = AnamnesisService(workspace_root=tmp_path / "workspace", home=home)
    codex = next(source for source in service.discover() if source.source_type == "codex")
    service.authorize(codex.source_id)

    assert service.index_authorized_sources() == {"chunks": 3, "documents": 3, "sources": 1}
    for index in range(3):
        assert service.search(f"incremental unique {index}")[0].session_id == f"session-{index}"


def test_same_stem_fallback_session_ids_do_not_collide(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source_root = home / ".codex" / "sessions"
    first_dir = source_root / "first"
    second_dir = source_root / "second"
    first_dir.mkdir(parents=True)
    second_dir.mkdir(parents=True)
    (first_dir / "session.txt").write_text("alpha same stem", encoding="utf-8")
    (second_dir / "session.txt").write_text("beta same stem", encoding="utf-8")

    service = AnamnesisService(workspace_root=tmp_path / "workspace", home=home)
    codex = next(source for source in service.discover() if source.source_type == "codex")
    service.authorize(codex.source_id)

    assert service.index_authorized_sources() == {"chunks": 2, "documents": 2, "sources": 1}
    alpha = service.search("alpha same stem")[0]
    beta = service.search("beta same stem")[0]

    assert alpha.session_id != beta.session_id
    assert alpha.session_id.startswith("session:")
    assert beta.session_id.startswith("session:")


def test_long_text_source_is_split_into_bounded_chunks(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source_root = home / ".codex" / "sessions"
    source_root.mkdir(parents=True)
    long_text = "alpha " + ("middle " * 900) + "omega"
    (source_root / "long-session.txt").write_text(long_text, encoding="utf-8")

    workspace = tmp_path / "workspace"
    service = AnamnesisService(workspace_root=workspace, home=home)
    codex = next(source for source in service.discover() if source.source_type == "codex")
    service.authorize(codex.source_id)

    counts = service.index_authorized_sources()
    with sqlite3.connect(workspace / "anamnesis.sqlite") as connection:
        chunk_texts = [
            row[0]
            for row in connection.execute(
                "SELECT text FROM chunks ORDER BY chunk_id"
            ).fetchall()
        ]

    assert counts == {"chunks": len(chunk_texts), "documents": 1, "sources": 1}
    assert len(chunk_texts) > 1
    assert all(len(text) <= MAX_TEXT_CHUNK_CHARS for text in chunk_texts)
    assert "alpha" in chunk_texts[0]
    assert "omega" in chunk_texts[-1]


def test_jsonl_malformed_line_indexes_as_unknown_text(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source_root = home / ".codex" / "sessions"
    source_root.mkdir(parents=True)
    (source_root / "mixed.jsonl").write_text(
        "\n".join(
            [
                "malformed jsonl secret",
                json.dumps({"role": "assistant", "content": "valid jsonl content"}),
            ]
        ),
        encoding="utf-8",
    )

    workspace = tmp_path / "workspace"
    service = AnamnesisService(workspace_root=workspace, home=home)
    codex = next(source for source in service.discover() if source.source_type == "codex")
    service.authorize(codex.source_id)

    assert service.index_authorized_sources() == {"chunks": 2, "documents": 1, "sources": 1}
    assert len(service.search("malformed jsonl secret")) == 1
    assert len(service.search("valid jsonl content")) == 1
    with sqlite3.connect(workspace / "anamnesis.sqlite") as connection:
        roles = [
            row[0]
            for row in connection.execute(
                "SELECT role FROM chunks ORDER BY chunk_id"
            ).fetchall()
        ]

    assert roles == ["unknown", "assistant"]


def test_malformed_vscode_sqlite_is_skipped_with_diagnostics(tmp_path: Path) -> None:
    home = tmp_path / "home"
    storage = home / ".config" / "Code" / "User" / "workspaceStorage" / "project"
    storage.mkdir(parents=True)
    bad_path = storage / "state.sqlite-journal"
    bad_path.write_text("not a sqlite database", encoding="utf-8")

    service = AnamnesisService(workspace_root=tmp_path / "workspace", home=home)
    copilot = next(
        source for source in service.discover() if source.source_type == "copilot_vscode"
    )
    service.authorize(copilot.source_id)

    assert service.index_authorized_sources() == {
        "chunks": 0,
        "documents": 0,
        "skipped_file_diagnostics": [
            {
                "path": str(bad_path),
                "reason": "sqlite_error: file is not a database",
            }
        ],
        "skipped_files": 1,
        "sources": 1,
    }


def test_vscode_storage_filters_unrelated_extension_rows(tmp_path: Path) -> None:
    home = tmp_path / "home"
    storage = home / ".config" / "Code" / "User" / "workspaceStorage" / "project"
    storage.mkdir(parents=True)
    db_path = storage / "state.vscdb"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE itemTable (row_id INTEGER PRIMARY KEY, key TEXT, value TEXT)"
        )
        connection.execute(
            "INSERT INTO itemTable(key, value) VALUES (?, ?)",
            (
                "copilot.session.auth",
                json.dumps(
                    {
                        "id": "auth",
                        "messages": [{"role": "user", "content": "copilot scoped"}],
                    }
                ),
            ),
        )
        connection.execute(
            "INSERT INTO itemTable(key, value) VALUES (?, ?)",
            (
                "chatty.extension.secret",
                json.dumps(
                    {
                        "id": "secret",
                        "messages": [{"role": "user", "content": "chatty extension secret"}],
                    }
                ),
            ),
        )

    service = AnamnesisService(workspace_root=tmp_path / "workspace", home=home)
    copilot = next(
        source for source in service.discover() if source.source_type == "copilot_vscode"
    )
    service.authorize(copilot.source_id)

    assert service.index_authorized_sources() == {"chunks": 1, "documents": 1, "sources": 1}
    assert len(service.search("copilot scoped")) == 1
    assert service.search("chatty extension secret") == ()


def test_vscode_indexing_never_reads_files_outside_discovered_scope(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    storage = home / ".config" / "Code" / "User" / "workspaceStorage" / "project"
    storage.mkdir(parents=True)
    (storage / "secret.txt").write_text("plain text storage secret", encoding="utf-8")
    (storage / "other.json").write_text(
        json.dumps(
            {
                "id": "json-secret",
                "messages": [{"role": "user", "content": "json storage secret"}],
            }
        ),
        encoding="utf-8",
    )

    service = AnamnesisService(workspace_root=tmp_path / "workspace", home=home)
    copilot = next(
        source for source in service.discover() if source.source_type == "copilot_vscode"
    )

    assert copilot.file_count == 0

    service.authorize(copilot.source_id)
    assert service.index_authorized_sources() == {"chunks": 0, "documents": 0, "sources": 1}
    assert service.search("plain text storage secret") == ()
    assert service.search("json storage secret") == ()


def test_search_treats_punctuation_as_plain_text(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source_root = home / ".codex" / "sessions"
    source_root.mkdir(parents=True)
    (source_root / "session.json").write_text(
        json.dumps(
            {
                "id": "auth-session",
                "messages": [{"role": "user", "content": "auth architecture notes"}],
            }
        ),
        encoding="utf-8",
    )

    service = AnamnesisService(workspace_root=tmp_path / "workspace", home=home)
    codex = next(source for source in service.discover() if source.source_type == "codex")
    service.authorize(codex.source_id)
    service.index_authorized_sources()

    assert service.search("auth:")[0].session_id == "auth-session"
    assert service.search(":") == ()
