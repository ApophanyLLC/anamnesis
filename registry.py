"""Governed Anamnesis source capability registry."""

from __future__ import annotations

from pathlib import Path

from .models import SourceDefinition


LOCAL_TEXT_SHAPES = ("json", "jsonl", "markdown", "text")
CHATGPT_EXPORT_SHAPES = ("openai-export-zip", "conversations-json")
CLOUD_ACCOUNT_EXPORT_SHAPES = ("account-export-zip", "account-export-json")
WORKSPACE_EXPORT_SHAPES = (
    "workspace-export-json",
    "workspace-export-markdown",
)
VSCODE_SQLITE_SHAPES = ("sqlite-db", "vscode-state-vscdb")
LM_STUDIO_SHAPES = ("lm-studio-conversation-json",)
JAN_SHAPES = ("jan-local-json",)
OPEN_WEBUI_SHAPES = (
    "open-webui-export-json",
    "open-webui-export-markdown",
    "open-webui-sqlite-db",
)
CODEX_CLI_SHAPES = ("codex-history-jsonl", "codex-session-jsonl")
COPILOT_CLI_SHAPES = ("copilot-cli-session-history",)
VSCODE_CHAT_EXPORT_SHAPES = ("vscode-chat-export-json", "vscode-state-vscdb")
UNVERIFIED_EXPORT_SHAPES = ("unverified-export-shape",)

EXPLICIT_EXPORT_STEPS = (
    "Export or download account/workspace data from the product UI.",
    "Place the export under the configured Anamnesis import root.",
    "Run discover, authorize, and index.",
)
LOCAL_DISCOVERY_STEPS = (
    "Review the discovered product-owned local path.",
    "Authorize the source explicitly.",
    "Run index.",
)
UNVERIFIED_STEPS = (
    "Verify a primary-source export path or local session path.",
    "Add source-specific parser and safety tests before activation.",
)

CLOUD_EXPORT_DRIFT = "Cloud export archive layouts and privacy UI labels may change."
LOCAL_SCHEMA_DRIFT = "Local storage paths and file schemas may change across app releases."
VSCODE_SCHEMA_DRIFT = "VS Code workspace storage and Copilot chat schemas are undocumented and may drift."
UNVERIFIED_DRIFT = "Export availability, local paths, and schemas are not verified."


SOURCE_CAPABILITY_REGISTRY: tuple[SourceDefinition, ...] = (
    SourceDefinition(
        source_type="claude",
        display_name="Claude Export",
        default_path=Path("~/Anamnesis/imports/claude"),
        file_suffixes=(".zip", ".json"),
        access_method="user_supplied_export",
        default_discovery_policy="manual_import_only",
        accepted_file_shapes=CLOUD_ACCOUNT_EXPORT_SHAPES,
        risk_level="high",
        parser_owner="parser_documents",
        storage_model="cloud_account_history_export",
        local_path_format="ZIP or JSON account export copied into ~/Anamnesis/imports/claude",
        user_access_steps=EXPLICIT_EXPORT_STEPS,
        confidence_level="high",
        drift_warning=CLOUD_EXPORT_DRIFT,
        notes="Cloud account-history product: import explicit Claude data exports only.",
    ),
    SourceDefinition(
        source_type="codex",
        display_name="Codex",
        default_path=Path("~/.codex/sessions"),
        file_suffixes=(".json", ".jsonl", ".txt", ".md"),
        access_method="local_files",
        default_discovery_policy="auto_discover_local",
        accepted_file_shapes=LOCAL_TEXT_SHAPES,
        risk_level="medium",
        parser_owner="parser_documents",
        storage_model="local_transcript_files",
        local_path_format="JSON, JSONL, Markdown, or text files under ~/.codex/sessions",
        user_access_steps=LOCAL_DISCOVERY_STEPS,
        confidence_level="high",
        drift_warning=LOCAL_SCHEMA_DRIFT,
        notes="Local Codex session files when present.",
    ),
    SourceDefinition(
        source_type="gemini_antigravity",
        display_name="Gemini Antigravity",
        default_path=Path("~/.gemini/antigravity/conversations"),
        file_suffixes=(".json", ".jsonl", ".txt", ".md"),
        access_method="local_files",
        default_discovery_policy="auto_discover_local",
        accepted_file_shapes=LOCAL_TEXT_SHAPES,
        risk_level="medium",
        parser_owner="parser_documents",
        storage_model="local_transcript_files",
        local_path_format="JSON, JSONL, Markdown, or text files under ~/.gemini/antigravity/conversations",
        user_access_steps=LOCAL_DISCOVERY_STEPS,
        confidence_level="medium",
        drift_warning=LOCAL_SCHEMA_DRIFT,
        notes="Local conversation files when present.",
    ),
    SourceDefinition(
        source_type="chatgpt_export",
        display_name="ChatGPT Export",
        default_path=Path("~/Anamnesis/chatgpt_exports"),
        file_suffixes=(".zip", ".json"),
        access_method="user_supplied_export",
        default_discovery_policy="manual_import_only",
        accepted_file_shapes=CHATGPT_EXPORT_SHAPES,
        risk_level="high",
        parser_owner="parser_documents",
        storage_model="cloud_account_history_export",
        local_path_format="OpenAI export ZIP or extracted conversations.json under ~/Anamnesis/chatgpt_exports",
        user_access_steps=EXPLICIT_EXPORT_STEPS,
        confidence_level="high",
        drift_warning=CLOUD_EXPORT_DRIFT,
        notes="Drop OpenAI export ZIPs or extracted conversations.json files here.",
    ),
    SourceDefinition(
        source_type="gemini_export",
        display_name="Gemini Export",
        default_path=Path("~/Anamnesis/imports/gemini"),
        file_suffixes=(".zip", ".json"),
        access_method="user_supplied_export",
        default_discovery_policy="manual_import_only",
        accepted_file_shapes=CLOUD_ACCOUNT_EXPORT_SHAPES,
        risk_level="high",
        parser_owner="parser_documents",
        storage_model="cloud_account_history_export",
        local_path_format="ZIP or JSON Gemini data export copied into ~/Anamnesis/imports/gemini",
        user_access_steps=EXPLICIT_EXPORT_STEPS,
        confidence_level="high",
        drift_warning=CLOUD_EXPORT_DRIFT,
        notes="Cloud account-history product: import explicit Gemini data exports only.",
    ),
    SourceDefinition(
        source_type="character_ai_export",
        display_name="Character.AI Export",
        default_path=Path("~/Anamnesis/imports/character_ai"),
        file_suffixes=(".zip", ".json"),
        access_method="user_supplied_export",
        default_discovery_policy="manual_import_only",
        accepted_file_shapes=CLOUD_ACCOUNT_EXPORT_SHAPES,
        risk_level="high",
        parser_owner="parser_documents",
        storage_model="cloud_account_history_export",
        local_path_format="ZIP or JSON Character.AI data export copied into ~/Anamnesis/imports/character_ai",
        user_access_steps=EXPLICIT_EXPORT_STEPS,
        confidence_level="high",
        drift_warning=CLOUD_EXPORT_DRIFT,
        notes="Cloud account-history product: import explicit Character.AI data exports only.",
    ),
    SourceDefinition(
        source_type="notion_export",
        display_name="Notion Export",
        default_path=Path("~/Anamnesis/imports/notion"),
        file_suffixes=(".zip", ".json", ".md"),
        access_method="user_supplied_export",
        default_discovery_policy="manual_import_only",
        accepted_file_shapes=WORKSPACE_EXPORT_SHAPES,
        risk_level="high",
        parser_owner="parser_documents",
        storage_model="cloud_workspace_export",
        local_path_format="Notion workspace/page export copied into ~/Anamnesis/imports/notion",
        user_access_steps=EXPLICIT_EXPORT_STEPS,
        confidence_level="high",
        drift_warning=CLOUD_EXPORT_DRIFT,
        notes="Workspace cloud product: import explicit Notion workspace/page exports only.",
    ),
    SourceDefinition(
        source_type="manual_import",
        display_name="Manual Import",
        default_path=Path("~/Anamnesis/imports"),
        file_suffixes=(".json", ".jsonl", ".txt", ".md"),
        access_method="user_supplied_folder",
        default_discovery_policy="manual_import_only",
        accepted_file_shapes=LOCAL_TEXT_SHAPES,
        risk_level="high",
        parser_owner="parser_documents",
        storage_model="user_supplied_files",
        local_path_format="JSON, JSONL, Markdown, or text files under ~/Anamnesis/imports",
        user_access_steps=(
            "Place specific export files in the manual import directory.",
            "Run discover, authorize, and index.",
        ),
        confidence_level="medium",
        drift_warning="Manual imports depend on the user-supplied file shape.",
        notes="Drop JSON, JSONL, Markdown, or text exports here.",
    ),
    SourceDefinition(
        source_type="copilot_vscode",
        display_name="VS Code Copilot/Chat Workspace Storage",
        default_path=Path("~/.config/Code/User/workspaceStorage"),
        file_suffixes=(".db", ".sqlite", ".sqlite-journal", ".vscdb"),
        access_method="local_sqlite",
        default_discovery_policy="auto_discover_local",
        accepted_file_shapes=VSCODE_SQLITE_SHAPES,
        risk_level="high",
        parser_owner="parser_copilot",
        storage_model="vscode_workspace_storage_sqlite",
        local_path_format=".db, .sqlite, .sqlite-journal, or .vscdb files under VS Code workspaceStorage",
        user_access_steps=LOCAL_DISCOVERY_STEPS,
        confidence_level="medium",
        drift_warning=VSCODE_SCHEMA_DRIFT,
        notes="Detects VS Code workspace storage SQLite files and reads only chat/Copilot-shaped records.",
    ),
    SourceDefinition(
        source_type="copilot_vscode",
        display_name="VS Code Insiders Copilot/Chat Workspace Storage",
        default_path=Path("~/.config/Code - Insiders/User/workspaceStorage"),
        file_suffixes=(".db", ".sqlite", ".sqlite-journal", ".vscdb"),
        access_method="local_sqlite",
        default_discovery_policy="auto_discover_local",
        accepted_file_shapes=VSCODE_SQLITE_SHAPES,
        risk_level="high",
        parser_owner="parser_copilot",
        storage_model="vscode_workspace_storage_sqlite",
        local_path_format=".db, .sqlite, .sqlite-journal, or .vscdb files under VS Code Insiders workspaceStorage",
        user_access_steps=LOCAL_DISCOVERY_STEPS,
        confidence_level="medium",
        drift_warning=VSCODE_SCHEMA_DRIFT,
        notes="Detects VS Code Insiders workspace storage SQLite files and reads only chat/Copilot-shaped records.",
    ),
    SourceDefinition(
        source_type="copilot_vscode",
        display_name="VS Code macOS Copilot/Chat Workspace Storage",
        default_path=Path("~/Library/Application Support/Code/User/workspaceStorage"),
        file_suffixes=(".db", ".sqlite", ".sqlite-journal", ".vscdb"),
        access_method="local_sqlite",
        default_discovery_policy="auto_discover_local",
        accepted_file_shapes=VSCODE_SQLITE_SHAPES,
        risk_level="high",
        parser_owner="parser_copilot",
        storage_model="vscode_workspace_storage_sqlite",
        local_path_format=".db, .sqlite, .sqlite-journal, or .vscdb files under macOS VS Code workspaceStorage",
        user_access_steps=LOCAL_DISCOVERY_STEPS,
        confidence_level="medium",
        drift_warning=VSCODE_SCHEMA_DRIFT,
        notes="Detects macOS VS Code workspace storage SQLite files and reads only chat/Copilot-shaped records.",
    ),
    SourceDefinition(
        source_type="copilot_vscode",
        display_name="VS Code macOS Insiders Copilot/Chat Workspace Storage",
        default_path=Path(
            "~/Library/Application Support/Code - Insiders/User/workspaceStorage"
        ),
        file_suffixes=(".db", ".sqlite", ".sqlite-journal", ".vscdb"),
        access_method="local_sqlite",
        default_discovery_policy="auto_discover_local",
        accepted_file_shapes=VSCODE_SQLITE_SHAPES,
        risk_level="high",
        parser_owner="parser_copilot",
        storage_model="vscode_workspace_storage_sqlite",
        local_path_format=".db, .sqlite, .sqlite-journal, or .vscdb files under macOS VS Code Insiders workspaceStorage",
        user_access_steps=LOCAL_DISCOVERY_STEPS,
        confidence_level="medium",
        drift_warning=VSCODE_SCHEMA_DRIFT,
        notes="Detects macOS VS Code Insiders workspace storage SQLite files and reads only chat/Copilot-shaped records.",
    ),
    SourceDefinition(
        source_type="copilot_vscode",
        display_name="VS Code Windows Copilot/Chat Workspace Storage",
        default_path=Path("~/AppData/Roaming/Code/User/workspaceStorage"),
        file_suffixes=(".db", ".sqlite", ".sqlite-journal", ".vscdb"),
        access_method="local_sqlite",
        default_discovery_policy="auto_discover_local",
        accepted_file_shapes=VSCODE_SQLITE_SHAPES,
        risk_level="high",
        parser_owner="parser_copilot",
        storage_model="vscode_workspace_storage_sqlite",
        local_path_format=".db, .sqlite, .sqlite-journal, or .vscdb files under Windows VS Code workspaceStorage",
        user_access_steps=LOCAL_DISCOVERY_STEPS,
        confidence_level="medium",
        drift_warning=VSCODE_SCHEMA_DRIFT,
        notes="Detects Windows VS Code workspace storage SQLite files and reads only chat/Copilot-shaped records.",
    ),
    SourceDefinition(
        source_type="copilot_vscode",
        display_name="VS Code Windows Insiders Copilot/Chat Workspace Storage",
        default_path=Path("~/AppData/Roaming/Code - Insiders/User/workspaceStorage"),
        file_suffixes=(".db", ".sqlite", ".sqlite-journal", ".vscdb"),
        access_method="local_sqlite",
        default_discovery_policy="auto_discover_local",
        accepted_file_shapes=VSCODE_SQLITE_SHAPES,
        risk_level="high",
        parser_owner="parser_copilot",
        storage_model="vscode_workspace_storage_sqlite",
        local_path_format=".db, .sqlite, .sqlite-journal, or .vscdb files under Windows VS Code Insiders workspaceStorage",
        user_access_steps=LOCAL_DISCOVERY_STEPS,
        confidence_level="medium",
        drift_warning=VSCODE_SCHEMA_DRIFT,
        notes="Detects Windows VS Code Insiders workspace storage SQLite files and reads only chat/Copilot-shaped records.",
    ),
)


DEFAULT_SOURCE_DEFINITIONS = SOURCE_CAPABILITY_REGISTRY


SOURCE_CAPABILITY_BACKLOG: tuple[SourceDefinition, ...] = (
    SourceDefinition(
        source_type="lm_studio",
        display_name="LM Studio",
        default_path=Path("~/.lmstudio/conversations"),
        file_suffixes=(".json",),
        access_method="local_files",
        default_discovery_policy="auto_discover_local",
        accepted_file_shapes=LM_STUDIO_SHAPES,
        risk_level="medium",
        parser_owner="parser_documents_candidate",
        storage_model="local_conversation_json",
        local_path_format="JSON conversation files under ~/.lmstudio/conversations",
        user_access_steps=LOCAL_DISCOVERY_STEPS,
        confidence_level="high",
        drift_warning=LOCAL_SCHEMA_DRIFT,
        notes="Backlog candidate: product-owned JSON conversation directory; verify schema before activation.",
    ),
    SourceDefinition(
        source_type="jan",
        display_name="Jan",
        default_path=Path("~/Library/Application Support/Jan/data"),
        file_suffixes=(".json",),
        access_method="local_files",
        default_discovery_policy="auto_discover_local",
        accepted_file_shapes=JAN_SHAPES,
        risk_level="medium",
        parser_owner="parser_documents_candidate",
        storage_model="local_app_data_json",
        local_path_format="JSON app data under Jan data folders such as ~/Library/Application Support/Jan/data",
        user_access_steps=LOCAL_DISCOVERY_STEPS,
        confidence_level="high",
        drift_warning=LOCAL_SCHEMA_DRIFT,
        notes=(
            "Backlog candidate: local-first app data folder. Also documented at "
            "%APPDATA%/Jan/data and ~/.local/share/Jan/data on other platforms."
        ),
    ),
    SourceDefinition(
        source_type="open_webui",
        display_name="Open WebUI",
        default_path=Path("~/Anamnesis/imports/openwebui"),
        file_suffixes=(".json", ".md", ".sqlite", ".db"),
        access_method="user_supplied_export",
        default_discovery_policy="manual_import_only",
        accepted_file_shapes=OPEN_WEBUI_SHAPES,
        risk_level="high",
        parser_owner="parser_openwebui_candidate",
        storage_model="self_hosted_export_or_database",
        local_path_format="Explicit Open WebUI export files or copied webui.db under ~/Anamnesis/imports/openwebui",
        user_access_steps=EXPLICIT_EXPORT_STEPS,
        confidence_level="high",
        drift_warning="Open WebUI database schema and export formats may change across releases.",
        notes=(
            "Backlog candidate: prefer explicit exports or copied webui.db files; "
            "do not auto-discover Docker volumes."
        ),
    ),
    SourceDefinition(
        source_type="codex",
        display_name="Codex CLI History",
        default_path=Path("~/.codex/history.jsonl"),
        file_suffixes=(".jsonl",),
        access_method="local_files",
        default_discovery_policy="auto_discover_local",
        accepted_file_shapes=CODEX_CLI_SHAPES,
        risk_level="medium",
        parser_owner="parser_documents_candidate",
        storage_model="local_jsonl_transcript_history",
        local_path_format="JSONL history file at ~/.codex/history.jsonl plus session JSONL files under ~/.codex/sessions",
        user_access_steps=LOCAL_DISCOVERY_STEPS,
        confidence_level="high",
        drift_warning=LOCAL_SCHEMA_DRIFT,
        notes=(
            "Backlog candidate complementing the active ~/.codex/sessions entry; "
            "history.jsonl needs transcript-aware normalization before activation."
        ),
    ),
    SourceDefinition(
        source_type="github_copilot_cli",
        display_name="GitHub Copilot CLI",
        default_path=Path("~/.copilot"),
        file_suffixes=(".json", ".jsonl", ".sqlite", ".db"),
        access_method="local_files",
        default_discovery_policy="auto_discover_local",
        accepted_file_shapes=COPILOT_CLI_SHAPES,
        risk_level="high",
        parser_owner="parser_copilot_cli_candidate",
        storage_model="local_cli_config_and_session_history",
        local_path_format="GitHub Copilot CLI config/session-history files under ~/.copilot",
        user_access_steps=LOCAL_DISCOVERY_STEPS,
        confidence_level="high",
        drift_warning=LOCAL_SCHEMA_DRIFT,
        notes=(
            "Backlog candidate: config directory may include logs and customization "
            "data, so activation needs narrow session-history filters."
        ),
    ),
    SourceDefinition(
        source_type="copilot_vscode",
        display_name="GitHub Copilot in VS Code",
        default_path=Path("~/Anamnesis/imports/vscode_chat_exports"),
        file_suffixes=(".json", ".vscdb"),
        access_method="local_files_or_user_supplied_export",
        default_discovery_policy="manual_import_only",
        accepted_file_shapes=VSCODE_CHAT_EXPORT_SHAPES,
        risk_level="high",
        parser_owner="parser_copilot_candidate",
        storage_model="vscode_export_or_workspace_storage",
        local_path_format="Exported VS Code chat JSON or copied state.vscdb under ~/Anamnesis/imports/vscode_chat_exports",
        user_access_steps=EXPLICIT_EXPORT_STEPS,
        confidence_level="high",
        drift_warning=VSCODE_SCHEMA_DRIFT,
        notes=(
            "Backlog candidate: active SQLite workspace storage discovery exists; "
            "future work should add schema-specific adapters and exported-chat JSON support."
        ),
    ),
    SourceDefinition(
        source_type="grok",
        display_name="xAI Grok",
        default_path=Path("~/Anamnesis/imports/grok"),
        file_suffixes=(),
        access_method="unverified_cloud_export",
        default_discovery_policy="docs_backlog_only",
        accepted_file_shapes=UNVERIFIED_EXPORT_SHAPES,
        risk_level="unknown",
        parser_owner="unassigned",
        storage_model="unverified_cloud_account_history",
        local_path_format="No verified local path or export schema",
        user_access_steps=UNVERIFIED_STEPS,
        confidence_level="low",
        drift_warning=UNVERIFIED_DRIFT,
        notes=(
            "Low-confidence backlog candidate: no verified primary-source bulk export "
            "or local session path. Do not add discovery until export behavior is tested."
        ),
    ),
    SourceDefinition(
        source_type="sai",
        display_name="Sai by Simular",
        default_path=Path("~/Anamnesis/imports/sai"),
        file_suffixes=(),
        access_method="unverified_cloud_or_device_export",
        default_discovery_policy="docs_backlog_only",
        accepted_file_shapes=UNVERIFIED_EXPORT_SHAPES,
        risk_level="unknown",
        parser_owner="unassigned",
        storage_model="unverified_cloud_or_device_history",
        local_path_format="No verified local path or export schema",
        user_access_steps=UNVERIFIED_STEPS,
        confidence_level="low",
        drift_warning=UNVERIFIED_DRIFT,
        notes=(
            "Low-confidence backlog candidate: session/export format not verified from "
            "primary documentation. Keep docs-only until tested directly."
        ),
    ),
    SourceDefinition(
        source_type="qwen",
        display_name="Qwen",
        default_path=Path("~/Anamnesis/imports/qwen"),
        file_suffixes=(),
        access_method="unverified_cloud_export",
        default_discovery_policy="docs_backlog_only",
        accepted_file_shapes=UNVERIFIED_EXPORT_SHAPES,
        risk_level="unknown",
        parser_owner="unassigned",
        storage_model="unverified_cloud_account_history",
        local_path_format="No verified local path or export schema",
        user_access_steps=UNVERIFIED_STEPS,
        confidence_level="low",
        drift_warning=UNVERIFIED_DRIFT,
        notes=(
            "Low-confidence backlog candidate: access/deletion rights were documented, "
            "but no verified chat export schema or local session path."
        ),
    ),
    SourceDefinition(
        source_type="poe",
        display_name="Poe",
        default_path=Path("~/Anamnesis/imports/poe"),
        file_suffixes=(),
        access_method="partially_verified_api_or_cloud_export",
        default_discovery_policy="docs_backlog_only",
        accepted_file_shapes=UNVERIFIED_EXPORT_SHAPES,
        risk_level="unknown",
        parser_owner="unassigned",
        storage_model="partially_verified_api_or_cloud_history",
        local_path_format="No verified consumer bulk export schema or local session path",
        user_access_steps=UNVERIFIED_STEPS,
        confidence_level="low",
        drift_warning=UNVERIFIED_DRIFT,
        notes=(
            "Partial-confidence backlog candidate: API conversation behavior exists, "
            "but consumer bulk chat export/local storage was not verified."
        ),
    ),
)


def definitions_by_source_type(
    definitions: tuple[SourceDefinition, ...] = SOURCE_CAPABILITY_REGISTRY,
) -> dict[str, SourceDefinition]:
    """Return the first governed capability record for each source type."""

    records: dict[str, SourceDefinition] = {}
    for definition in definitions:
        records.setdefault(definition.source_type, definition)
    return records


def definitions_by_definition_id(
    definitions: tuple[SourceDefinition, ...] = SOURCE_CAPABILITY_REGISTRY,
) -> dict[str, SourceDefinition]:
    """Return every governed capability record by its policy snapshot id."""

    return {definition.definition_id: definition for definition in definitions}


def definition_for_source_type(
    source_type: str,
    definitions: tuple[SourceDefinition, ...] = SOURCE_CAPABILITY_REGISTRY,
) -> SourceDefinition | None:
    return definitions_by_source_type(definitions).get(source_type)


def definition_for_definition_id(
    definition_id: str,
    definitions: tuple[SourceDefinition, ...] = SOURCE_CAPABILITY_REGISTRY,
) -> SourceDefinition | None:
    return definitions_by_definition_id(definitions).get(definition_id)


def backlog_by_source_type(
    definitions: tuple[SourceDefinition, ...] = SOURCE_CAPABILITY_BACKLOG,
) -> dict[str, SourceDefinition]:
    """Return governed source candidates that are not active discovery defaults."""

    return definitions_by_source_type(definitions)
