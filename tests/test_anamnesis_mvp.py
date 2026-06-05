from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3
import json
from pathlib import Path
import subprocess
import sys
import tomllib
import zipfile

from anamnesis import cli as anamnesis_cli
from anamnesis.index import AnamnesisSearchError
from anamnesis.registry import (
    SOURCE_CAPABILITY_BACKLOG,
    SOURCE_CAPABILITY_REGISTRY,
    backlog_by_source_type,
    definitions_by_source_type,
)
from anamnesis.service import AnamnesisService


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_anamnesis_public_module_and_console_script_metadata_agree() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["scripts"]["anamnesis"] == "anamnesis.__main__:main"

    completed = subprocess.run(
        [sys.executable, "-m", "anamnesis", "versions"],
        capture_output=True,
        cwd=REPO_ROOT,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["app"] == "anamnesis"


def test_anamnesis_readme_distinguishes_repo_and_snapshot_commands() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "installable standalone package" in readme
    assert "python -m pytest tests" in readme
    assert "python -m pip install -e ." in readme
    assert "anamnesis discover" in readme


def test_anamnesis_discover_authorize_index_search_and_revoke(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source_root = home / ".codex" / "sessions"
    source_root.mkdir(parents=True)
    session_path = source_root / "session.json"
    session_path.write_text(
        json.dumps(
            {
                "id": "session-1",
                "title": "Auth Architecture",
                "messages": [
                    {
                        "role": "user",
                        "content": "Where did we decide the auth architecture?",
                    },
                    {
                        "role": "assistant",
                        "content": "Use local-first tokens and a revocation ledger.",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    service = AnamnesisService(workspace_root=tmp_path / "workspace", home=home)
    discovered = service.discover()
    codex = next(source for source in discovered if source.source_type == "codex")

    assert codex.file_count == 1
    assert codex.authorized is False

    service.authorize(codex.source_id)
    index_summary = service.index_authorized_sources()

    assert index_summary == {"chunks": 2, "documents": 1, "sources": 1}
    with sqlite3.connect(tmp_path / "workspace" / "anamnesis.sqlite") as connection:
        source_rows = connection.execute(
            "SELECT source_id, source_type, display_name, path FROM sources"
        ).fetchall()
    assert source_rows == [
        (
            codex.source_id,
            "codex",
            "Codex",
            str(source_root),
        )
    ]

    results = service.search("revocation", limit=3)
    assert len(results) == 1
    assert results[0].session_id == "session-1"
    assert results[0].title == "Auth Architecture"

    purged = service.revoke(codex.source_id)
    assert purged == 2
    with sqlite3.connect(tmp_path / "workspace" / "anamnesis.sqlite") as connection:
        assert connection.execute("SELECT * FROM sources").fetchall() == []
    assert service.search("revocation", limit=3) == ()


def test_anamnesis_sources_expose_governed_capability_registry(tmp_path: Path) -> None:
    home = tmp_path / "home"
    (home / ".claude" / "sessions").mkdir(parents=True)
    (home / ".claude" / "sessions" / "cloud-leak.json").write_text(
        json.dumps({"messages": [{"role": "user", "content": "do not discover"}]}),
        encoding="utf-8",
    )
    (home / ".codex" / "sessions").mkdir(parents=True)
    (home / "Anamnesis" / "chatgpt_exports").mkdir(parents=True)
    (home / "Anamnesis" / "imports" / "claude").mkdir(parents=True)
    (home / "Anamnesis" / "imports" / "gemini").mkdir(parents=True)
    (home / "Anamnesis" / "imports" / "character_ai").mkdir(parents=True)
    (home / "Anamnesis" / "imports" / "notion").mkdir(parents=True)
    (home / ".config" / "Code" / "User" / "workspaceStorage").mkdir(parents=True)

    registry = definitions_by_source_type()
    assert registry["chatgpt_export"].default_discovery_policy == "manual_import_only"
    assert registry["chatgpt_export"].risk_level == "high"
    assert registry["chatgpt_export"].accepted_file_shapes == (
        "openai-export-zip",
        "conversations-json",
    )
    for cloud_source_type in (
        "claude",
        "gemini_export",
        "character_ai_export",
        "notion_export",
    ):
        assert registry[cloud_source_type].access_method == "user_supplied_export"
        assert registry[cloud_source_type].default_discovery_policy == "manual_import_only"
        assert registry[cloud_source_type].risk_level == "high"
        assert registry[cloud_source_type].storage_model in {
            "cloud_account_history_export",
            "cloud_workspace_export",
        }
        assert registry[cloud_source_type].confidence_level == "high"
        assert registry[cloud_source_type].drift_warning
    assert registry["copilot_vscode"].file_suffixes == (
        ".db",
        ".sqlite",
        ".sqlite-journal",
        ".vscdb",
    )
    assert registry["copilot_vscode"].parser_owner == "parser_copilot"
    assert registry["copilot_vscode"].storage_model == "vscode_workspace_storage_sqlite"
    assert registry["copilot_vscode"].confidence_level == "medium"

    service = AnamnesisService(workspace_root=tmp_path / "workspace", home=home)
    discovered = service.discover()
    claude = next(source for source in discovered if source.source_type == "claude")
    chatgpt = next(source for source in discovered if source.source_type == "chatgpt_export")
    gemini = next(source for source in discovered if source.source_type == "gemini_export")
    character_ai = next(
        source for source in discovered if source.source_type == "character_ai_export"
    )
    notion = next(source for source in discovered if source.source_type == "notion_export")
    copilot = next(source for source in discovered if source.source_type == "copilot_vscode")

    assert claude.path == home / "Anamnesis" / "imports" / "claude"
    assert claude.default_discovery_policy == "manual_import_only"
    assert claude.file_count == 0
    assert claude.storage_model == "cloud_account_history_export"
    assert claude.local_path_format
    assert claude.user_access_steps
    assert claude.confidence_level == "high"
    assert claude.drift_warning
    assert chatgpt.default_discovery_policy == "manual_import_only"
    assert chatgpt.access_method == "user_supplied_export"
    assert chatgpt.risk_level == "high"
    assert chatgpt.parser_owner == "parser_documents"
    assert gemini.default_discovery_policy == "manual_import_only"
    assert character_ai.default_discovery_policy == "manual_import_only"
    assert notion.default_discovery_policy == "manual_import_only"
    assert copilot.default_discovery_policy == "auto_discover_local"
    assert copilot.accepted_file_shapes == ("sqlite-db", "vscode-state-vscdb")


def test_anamnesis_registry_entries_include_storage_matrix_governance_fields() -> None:
    for definition in (*SOURCE_CAPABILITY_REGISTRY, *SOURCE_CAPABILITY_BACKLOG):
        assert definition.storage_model
        assert definition.local_path_format
        assert definition.user_access_steps
        assert definition.confidence_level in {"high", "medium", "low"}
        assert definition.drift_warning


def test_anamnesis_registry_backlog_seeds_local_direct_file_candidates() -> None:
    active_registry = definitions_by_source_type()
    backlog = backlog_by_source_type()

    assert {
        "lm_studio",
        "jan",
        "open_webui",
        "codex",
        "github_copilot_cli",
        "copilot_vscode",
    } <= set(backlog)
    assert "lm_studio" not in active_registry
    assert "jan" not in active_registry
    assert "open_webui" not in active_registry
    assert "github_copilot_cli" not in active_registry

    assert backlog["lm_studio"].default_path == Path("~/.lmstudio/conversations")
    assert backlog["lm_studio"].accepted_file_shapes == (
        "lm-studio-conversation-json",
    )
    assert backlog["jan"].accepted_file_shapes == ("jan-local-json",)
    assert backlog["open_webui"].default_discovery_policy == "manual_import_only"
    assert backlog["open_webui"].risk_level == "high"
    assert backlog["codex"].accepted_file_shapes == (
        "codex-history-jsonl",
        "codex-session-jsonl",
    )
    assert backlog["github_copilot_cli"].default_path == Path("~/.copilot")
    assert backlog["github_copilot_cli"].risk_level == "high"
    assert backlog["copilot_vscode"].default_discovery_policy == "manual_import_only"


def test_anamnesis_registry_keeps_low_confidence_products_docs_backlog_only() -> None:
    active_registry = definitions_by_source_type()
    backlog = backlog_by_source_type()

    low_confidence_sources = {"grok", "sai", "qwen", "poe"}

    assert low_confidence_sources <= set(backlog)
    assert low_confidence_sources.isdisjoint(active_registry)
    for source_type in low_confidence_sources:
        definition = backlog[source_type]
        assert definition.default_discovery_policy == "docs_backlog_only"
        assert definition.file_suffixes == ()
        assert definition.accepted_file_shapes == ("unverified-export-shape",)
        assert definition.risk_level == "unknown"
        assert definition.parser_owner == "unassigned"
        assert definition.confidence_level == "low"
        assert definition.storage_model.startswith(("unverified", "partially_verified"))
        assert "not verified" in definition.drift_warning


def test_anamnesis_reindex_purges_deleted_source_files(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source_root = home / ".codex" / "sessions"
    source_root.mkdir(parents=True)
    session_path = source_root / "session.json"
    session_path.write_text(
        json.dumps(
            {
                "id": "session-ghost",
                "title": "Deleted Session",
                "messages": [
                    {"role": "user", "content": "This contains stale ghost term."},
                ],
            }
        ),
        encoding="utf-8",
    )

    service = AnamnesisService(workspace_root=tmp_path / "workspace", home=home)
    codex = next(source for source in service.discover() if source.source_type == "codex")
    service.authorize(codex.source_id)

    assert service.index_authorized_sources() == {"chunks": 1, "documents": 1, "sources": 1}
    assert len(service.search("stale ghost term", limit=3)) == 1

    session_path.unlink()

    assert service.index_authorized_sources() == {"chunks": 0, "documents": 0, "sources": 1}
    assert service.search("stale ghost term", limit=3) == ()


def test_anamnesis_json_list_indexes_all_conversations(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source_root = home / ".codex" / "sessions"
    source_root.mkdir(parents=True)
    session_path = source_root / "conversations.json"
    session_path.write_text(
        json.dumps(
            [
                {
                    "id": "c1",
                    "messages": [{"role": "user", "content": "alpha unique"}],
                },
                {
                    "id": "c2",
                    "messages": [{"role": "user", "content": "beta unique"}],
                },
            ]
        ),
        encoding="utf-8",
    )

    service = AnamnesisService(workspace_root=tmp_path / "workspace", home=home)
    codex = next(source for source in service.discover() if source.source_type == "codex")
    service.authorize(codex.source_id)

    assert service.index_authorized_sources() == {"chunks": 2, "documents": 2, "sources": 1}
    assert service.search("alpha unique", limit=3)[0].session_id == "c1"
    assert service.search("beta unique", limit=3)[0].session_id == "c2"


def test_anamnesis_chatgpt_mapping_uses_parent_child_order(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source_root = home / ".codex" / "sessions"
    source_root.mkdir(parents=True)
    session_path = source_root / "mapping.json"
    session_path.write_text(
        json.dumps(
            {
                "id": "mapped-chat",
                "title": "Mapped Chat",
                "mapping": {
                    "assistant": {
                        "id": "assistant",
                        "parent": "user",
                        "children": [],
                        "message": {
                            "author": {"role": "assistant"},
                            "content": {"parts": ["second mapped reply"]},
                        },
                    },
                    "root": {
                        "id": "root",
                        "parent": None,
                        "children": ["user"],
                        "message": None,
                    },
                    "user": {
                        "id": "user",
                        "parent": "root",
                        "children": ["assistant"],
                        "message": {
                            "author": {"role": "user"},
                            "content": {"parts": ["first mapped prompt"]},
                        },
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    service = AnamnesisService(workspace_root=tmp_path / "workspace", home=home)
    codex = next(source for source in service.discover() if source.source_type == "codex")
    service.authorize(codex.source_id)

    assert service.index_authorized_sources() == {"chunks": 2, "documents": 1, "sources": 1}
    with sqlite3.connect(tmp_path / "workspace" / "anamnesis.sqlite") as connection:
        rows = connection.execute(
            "SELECT role, text FROM chunks WHERE session_id = ? ORDER BY chunk_id",
            ("mapped-chat",),
        ).fetchall()

    assert rows == [
        ("user", "first mapped prompt"),
        ("assistant", "second mapped reply"),
    ]


def test_anamnesis_text_files_are_split_into_bounded_chunks(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source_root = home / ".codex" / "sessions"
    source_root.mkdir(parents=True)
    long_text = "\n\n".join(
        f"section {index} " + ("long searchable text " * 80)
        for index in range(8)
    )
    (source_root / "long.txt").write_text(long_text, encoding="utf-8")

    service = AnamnesisService(workspace_root=tmp_path / "workspace", home=home)
    codex = next(source for source in service.discover() if source.source_type == "codex")
    service.authorize(codex.source_id)

    index_summary = service.index_authorized_sources()
    assert index_summary["documents"] == 1
    assert index_summary["chunks"] > 1
    with sqlite3.connect(tmp_path / "workspace" / "anamnesis.sqlite") as connection:
        chunk_lengths = [
            row[0]
            for row in connection.execute(
                "SELECT length(text) FROM chunks WHERE source_id = ?",
                (codex.source_id,),
            )
        ]

    assert max(chunk_lengths) <= 4000
    assert service.search("section 7", limit=3)


def test_anamnesis_search_treats_punctuation_as_plain_text(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source_root = home / ".codex" / "sessions"
    source_root.mkdir(parents=True)
    session_path = source_root / "session.json"
    session_path.write_text(
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

    assert service.search("auth:", limit=3)[0].session_id == "auth-session"
    assert service.search(":", limit=3) == ()


def test_anamnesis_chatgpt_export_uses_dedicated_import_directory(
    tmp_path: Path,
) -> None:
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
    assert service.search("dedicated export", limit=3)[0].session_id == "chatgpt-export"
    assert service.search("downloads secret", limit=3) == ()


def test_anamnesis_chatgpt_export_ignores_unrelated_zip_and_json(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    export_root = home / "Anamnesis" / "chatgpt_exports"
    export_root.mkdir(parents=True)
    (export_root / "taxes.json").write_text(
        json.dumps({"content": "unrelated private tax payload"}),
        encoding="utf-8",
    )
    with zipfile.ZipFile(export_root / "random.zip", "w") as archive:
        archive.writestr(
            "private.json",
            json.dumps({"content": "unrelated private zip payload"}),
        )
    with zipfile.ZipFile(export_root / "chatgpt.zip", "w") as archive:
        archive.writestr(
            "conversations.json",
            json.dumps(
                [
                    {
                        "id": "chatgpt-zip",
                        "messages": [{"role": "user", "content": "valid export zip"}],
                    }
                ]
            ),
        )
        archive.writestr(
            "user.json",
            json.dumps({"content": "profile data should not be indexed"}),
        )

    service = AnamnesisService(workspace_root=tmp_path / "workspace", home=home)
    chatgpt = next(
        source for source in service.discover() if source.source_type == "chatgpt_export"
    )

    assert chatgpt.file_count == 1

    service.authorize(chatgpt.source_id)
    assert service.index_authorized_sources() == {"chunks": 1, "documents": 1, "sources": 1}
    assert service.search("valid export zip", limit=3)[0].session_id == "chatgpt-zip"
    assert service.search("private tax", limit=3) == ()
    assert service.search("private zip", limit=3) == ()
    assert service.search("profile data", limit=3) == ()


def test_anamnesis_cli_reports_structured_search_errors(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    def raise_search_error(self, query: str, *, limit: int = 10):
        raise AnamnesisSearchError("invalid search query")

    monkeypatch.setattr(AnamnesisService, "search", raise_search_error)

    exit_code = anamnesis_cli.main(
        ["--workspace", str(tmp_path / "workspace"), "search", "auth:"]
    )

    assert exit_code == 2
    captured = capsys.readouterr()
    assert json.loads(captured.err) == {
        "error": {
            "code": "invalid_search_query",
            "message": "invalid search query",
        }
    }
    assert captured.out == ""


def test_anamnesis_vscode_copilot_sqlite_parser(tmp_path: Path) -> None:
    home = tmp_path / "home"
    copilot_storage = home / ".config" / "Code" / "User" / "workspaceStorage" / "project"
    copilot_storage.mkdir(parents=True)
    db_path = copilot_storage / "state.vscdb"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE itemTable (row_id INTEGER PRIMARY KEY, key TEXT, value TEXT)"
        )
        connection.execute(
            "INSERT INTO itemTable(key, value) VALUES (?, ?)",
            (
                "copilot.session.abc",
                json.dumps(
                    {
                        "id": "abc",
                        "title": "Copilot Session",
                        "messages": [
                            {"role": "user", "content": "Draft auth strategy for API keys"},
                            {"role": "assistant", "content": "Use per-session token vault."},
                        ],
                    }
                ),
            ),
        )
        connection.commit()

    service = AnamnesisService(workspace_root=tmp_path / "workspace", home=home)
    discovered = service.discover()
    copilot = next(
        source for source in discovered if source.source_type == "copilot_vscode"
    )

    assert copilot.file_count == 1

    service.authorize(copilot.source_id)
    index_summary = service.index_authorized_sources()
    assert index_summary["sources"] == 1
    assert index_summary["documents"] == 1
    assert index_summary["chunks"] == 2

    results = service.search("token vault", limit=5)
    assert len(results) == 1
    assert results[0].title == "Copilot Session"


def test_anamnesis_vscode_malformed_sqlite_files_are_skipped(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    copilot_storage = home / ".config" / "Code" / "User" / "workspaceStorage" / "project"
    copilot_storage.mkdir(parents=True)
    bad_path = copilot_storage / "state.sqlite-journal"
    bad_path.write_text("not a sqlite database", encoding="utf-8")

    service = AnamnesisService(workspace_root=tmp_path / "workspace", home=home)
    copilot = next(
        source for source in service.discover() if source.source_type == "copilot_vscode"
    )

    assert copilot.file_count == 1

    service.authorize(copilot.source_id)
    index_summary = service.index_authorized_sources()

    assert index_summary["sources"] == 1
    assert index_summary["documents"] == 0
    assert index_summary["chunks"] == 0
    assert index_summary["skipped_files"] == 1
    assert index_summary["skipped_file_diagnostics"] == [
        {
            "path": str(bad_path),
            "reason": "sqlite_error: file is not a database",
        }
    ]


def test_anamnesis_vscode_copilot_sqlite_filters_to_chat_scoped_records(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    copilot_storage = home / ".config" / "Code" / "User" / "workspaceStorage" / "project"
    copilot_storage.mkdir(parents=True)
    db_path = copilot_storage / "state.vscdb"
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
                        "title": "Auth Session",
                        "messages": [
                            {"role": "user", "content": "What is the secret for token rotation?"},
                            {
                                "role": "assistant",
                                "content": "Rotate signing tokens quarterly.",
                            },
                        ],
                    }
                ),
            ),
        )
        connection.execute(
            "INSERT INTO itemTable(key, value) VALUES (?, ?)",
            (
                "unrelated.extension.secret",
                json.dumps(
                    {
                        "id": "unrelated-secret",
                        "title": "Extension Secret",
                        "messages": [
                            {
                                "role": "user",
                                "content": "Do not index extension secret payload.",
                            },
                        ],
                    }
                ),
            ),
        )
        connection.execute(
            "CREATE TABLE chat_history (row_id INTEGER PRIMARY KEY, session_id TEXT, messages_payload TEXT)"
        )
        connection.execute(
            "INSERT INTO chat_history(session_id, messages_payload) VALUES (?, ?)",
            (
                "legacy-1",
                json.dumps(
                    {
                        "messages": [
                            {"role": "user", "content": "Need API usage pattern"},
                            {"role": "assistant", "content": "Use session signatures for retries."},
                        ]
                    }
                ),
            ),
        )
        connection.execute(
            "CREATE TABLE sessions (row_id INTEGER PRIMARY KEY, sessionId TEXT, messages TEXT)"
        )
        connection.execute(
            "INSERT INTO sessions(sessionId, messages) VALUES (?, ?)",
            (
                "legacy-session-2",
                json.dumps(
                    {
                        "messages": [
                            {"role": "user", "content": "How should we rollback keys?"},
                            {"role": "assistant", "content": "Use short-lived rotating tokens."},
                        ]
                    }
                ),
            ),
        )
        connection.execute(
            "CREATE TABLE mixed_case_schema (row_id INTEGER PRIMARY KEY, SESSION_ID TEXT, MESSAGES_PAYLOAD TEXT)"
        )
        connection.execute(
            "INSERT INTO mixed_case_schema(SESSION_ID, MESSAGES_PAYLOAD) VALUES (?, ?)",
            (
                "mixed-legacy-3",
                json.dumps(
                    {
                        "messages": [
                            {"role": "user", "content": "Any audit trail recommendations?"},
                            {
                                "role": "assistant",
                                "content": "Create rotation windows and immutable logs.",
                            },
                        ]
                    }
                ),
            ),
        )
        connection.execute(
            "CREATE TABLE copilot_blob_schema (row_id INTEGER PRIMARY KEY, session_id TEXT, messages_payload BLOB)"
        )
        connection.execute(
            "INSERT INTO copilot_blob_schema(session_id, messages_payload) VALUES (?, ?)",
            (
                "blob-legacy-4",
                json.dumps(
                    {
                        "messages": [
                            {"role": "user", "content": "Can we store payloads as bytes?"},
                            {"role": "assistant", "content": "Yes, and parser should decode them safely."},
                        ]
                    }
                ).encode("utf-8"),
            ),
        )
        connection.execute(
            "CREATE TABLE noise_log (row_id INTEGER PRIMARY KEY, created_at INTEGER, event_code INTEGER)"
        )
        connection.execute(
            "INSERT INTO noise_log(created_at, event_code) VALUES (?, ?)",
            (1700000000, 7),
        )
        connection.commit()

    service = AnamnesisService(workspace_root=tmp_path / "workspace", home=home)
    discovered = service.discover()
    copilot = next(
        source for source in discovered if source.source_type == "copilot_vscode"
    )

    service.authorize(copilot.source_id)
    index_summary = service.index_authorized_sources()
    assert index_summary["sources"] == 1
    assert index_summary["documents"] == 3
    assert index_summary["chunks"] == 6

    auth_results = service.search("rotate", limit=5)
    assert len(auth_results) == 1
    assert auth_results[0].title == "Auth Session"

    legacy_results = service.search("session signatures", limit=5)
    assert len(legacy_results) == 1
    assert "chat_history" in legacy_results[0].title

    assert service.search("rotating tokens", limit=5) == ()

    assert service.search("audit trail", limit=5) == ()

    blob_results = service.search("bytes", limit=5)
    assert len(blob_results) == 1
    assert "copilot_blob_schema" in blob_results[0].title

    assert service.search("extension secret", limit=5) == ()


def test_anamnesis_status_and_sync_health_surface_staleness(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source_root = home / ".codex" / "sessions"
    source_root.mkdir(parents=True)
    session_path = source_root / "session.json"
    session_path.write_text(
        json.dumps(
            {
                "id": "auth-session",
                "messages": [{"role": "user", "content": "status smoke test content"}],
            }
        ),
        encoding="utf-8",
    )

    service = AnamnesisService(workspace_root=tmp_path / "workspace", home=home)
    codex = next(source for source in service.discover() if source.source_type == "codex")
    service.authorize(codex.source_id)
    index_summary = service.index_authorized_sources()
    assert index_summary["sources"] == 1

    status = service.status()
    source_status = next(
        item for item in status["sources"] if item["source_id"] == codex.source_id
    )
    assert source_status["status"] == "success"
    assert source_status["parser_mode"] == "structured"
    assert source_status["drift_detected"] is False

    workspace_db = tmp_path / "workspace" / "anamnesis.sqlite"
    stale_time = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
    with sqlite3.connect(workspace_db) as connection:
        connection.execute(
            "UPDATE sources SET last_indexed_at = ? WHERE source_id = ?",
            (stale_time, codex.source_id),
        )
    health = service.sync_health()
    assert health["has_issues"] is True
    assert health["issues"] == [
        {"source_id": codex.source_id, "reason": "not_recent"}
    ]
