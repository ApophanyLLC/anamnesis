"""CLI for the Anamnesis local session archaeology app."""

from __future__ import annotations

import argparse
from dataclasses import asdict, is_dataclass
from datetime import datetime
import json
from pathlib import Path
import platform
import sys
from typing import Any

from . import __version__
from .index import AnamnesisSearchError
from .models import (
    SearchResult,
    SourceAuthorization,
    policy_id_for_snapshot,
    policy_snapshot_for_definition,
)
from .service import AnamnesisService
from .registry import definitions_by_source_type



_MANUAL_EXPORT_ASSISTANCE = {
    "claude": (
        "Claude: open your export/download page and export chat data",
        "Place exported JSON files in the configured import path.",
        "Keep the export in the exported folder until indexing succeeds.",
    ),
    "chatgpt_export": (
        "ChatGPT: open Settings → Data Controls → Export data (JSON/ZIP).",
        "Keep the exported ZIP or conversations.json under the import path.",
        "Anamnesis reads only OpenAI export payloads from that folder.",
    ),
    "gemini_export": (
        "Google Gemini: generate a conversation or account export from your account settings.",
        "Place the exported ZIP or JSON files in the configured import path.",
        "Keep the archive at the configured import path until indexing is complete.",
    ),
    "character_ai_export": (
        "Character.AI: request your data export from account settings.",
        "Copy the exported JSON file into the configured import path.",
        "Do not run indexing before authorization.",
    ),
    "notion_export": (
        "Notion: export relevant workspace pages or workspace exports.",
        "Drop JSON, Markdown, or workspace export files into the configured import path.",
        "Choose an export format that preserves conversation-relevant text.",
    ),
}


def _json_default(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _print_json(payload: Any, *, file: Any = None) -> None:
    print(json.dumps(payload, default=_json_default, indent=2, sort_keys=True), file=file)


def _manual_import_entry(source: Any) -> dict[str, Any]:
    instructions = list(source.user_access_steps)
    for hint in _MANUAL_EXPORT_ASSISTANCE.get(source.source_type, ()):
        if hint not in instructions:
            instructions.append(hint)
    return {
        "source_type": source.source_type,
        "display_name": source.display_name,
        "path": str(source.path),
        "path_notes": source.local_path_format,
        "instructions": instructions,
        "accepted_file_shapes": source.accepted_file_shapes,
    }


def _build_discover_tour(sources: tuple[Any, ...]) -> dict[str, Any]:
    manual_import_sources = [
        source
        for source in sources
        if source.default_discovery_policy == "manual_import_only"
    ]
    manual_import_paths = [
        _manual_import_entry(source)
        for source in manual_import_sources
        if source.path is not None
    ]
    has_authorized_source = False
    for source in sources:
        if source.authorized:
            has_authorized_source = True
            break
    tutorial = [
        "Cloud products are manual-only in this release.",
        "For each source below, run: copy exports into path -> authorize -> index.",
        "When exports are ready, run `anamnesis authorize <source_id>` for each source.",
        "After authorization, run `anamnesis index` to ingest content.",
    ]
    if has_authorized_source:
        tutorial = tutorial[1:]
    return {
        "manual_import_paths": manual_import_paths,
        "first_run_tour": tutorial,
    }


def _enrich_search_results(
    results: tuple[SearchResult, ...],
    *,
    source_status_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    source_status_by_id = {
        source_row["source_id"]: source_row for source_row in source_status_rows
    }
    enriched: list[dict[str, Any]] = []
    for result in results:
        source_status = source_status_by_id.get(result.source_id)
        parser_mode = source_status.get("parser_mode") if source_status else "unknown"
        parser_mode_label = (
            source_status.get("parser_mode_label")
            if source_status
            else "Structured Chat"
        )
        chunking_tooltip = (
            source_status.get("parser_mode_chunking_tooltip")
            if source_status
            else "Structured parser preserves message boundaries and metadata."
        )
        enriched.append(
            {
                **asdict(result),
                "parser_mode": parser_mode,
                "source_mode_label": parser_mode_label,
                "chunking_tooltip": chunking_tooltip,
                "title_with_mode": f"[{parser_mode_label}] {result.title}",
            }
        )
    return enriched


def _serialize_policy_value(value: object) -> list[str]:
    return json.dumps(value, sort_keys=True, indent=2).splitlines()


def _policy_diff_lines(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    keys = tuple(sorted(set(old.keys()) | set(new.keys())))
    lines: list[str] = []
    for key in keys:
        old_value = old.get(key)
        new_value = new.get(key)
        if old_value == new_value:
            continue
        lines.append(f"  {key}:")
        for line in _serialize_policy_value(old_value):
            lines.append(f"-   {line}")
        for line in _serialize_policy_value(new_value):
            lines.append(f"+   {line}")
    return lines


def _policy_escalation_detected(old: dict[str, Any], new: dict[str, Any]) -> bool:
    risk_order = {"low": 0, "medium": 1, "high": 2}
    if risk_order.get(str(new.get("risk_level", "")), 0) > risk_order.get(
        str(old.get("risk_level", "")), 0
    ):
        return True
    old_shapes = sorted(str(value) for value in old.get("accepted_file_shapes", ()))
    new_shapes = sorted(str(value) for value in new.get("accepted_file_shapes", ()))
    if len(set(new_shapes) - set(old_shapes)) > 0:
        return True
    old_suffixes = sorted(str(value) for value in old.get("file_suffixes", ()))
    new_suffixes = sorted(str(value) for value in new.get("file_suffixes", ()))
    if len(set(new_suffixes) - set(old_suffixes)) > 0:
        return True

    boundary_keys = {
        "local_path_format",
        "access_method",
        "storage_model",
        "default_discovery_policy",
    }
    return any(old.get(key) != new.get(key) for key in boundary_keys)


def _policy_expansion_only(old: dict[str, Any], new: dict[str, Any]) -> bool:
    if _policy_escalation_detected(old, new):
        return False
    non_expansive_keys = {
        "drift_warning",
        "default_discovery_policy",
        "notes",
        "parser_owner",
        "display_name",
        "source_type",
    }
    for key in old.keys() | new.keys():
        if key in non_expansive_keys:
            continue
        if old.get(key) != new.get(key):
            return False
    return True


def _prompt_authorize_with_policy_review(
    service: AnamnesisService, source_id: str, *, auto_approve: bool
) -> SourceAuthorization | None:
    source = next(
        (item for item in service.discover() if item.source_id == source_id), None
    )
    if source is None:
        raise KeyError(f"unknown source_id: {source_id}")
    authorization = service.authorization_store.get(source_id)
    if authorization is None or not authorization.policy_snapshot:
        return service.authorize(source_id)

    source_definitions = definitions_by_source_type()
    source_definition = source_definitions.get(source.source_type)
    if source_definition is None:
        return service.authorize(source_id)

    current_snapshot = policy_snapshot_for_definition(source_definition)
    current_policy_id = policy_id_for_snapshot(current_snapshot)
    if (
        authorization.policy_snapshot == current_snapshot
        and authorization.policy_id == current_policy_id
    ):
        return authorization

    if _policy_expansion_only(authorization.policy_snapshot, current_snapshot):
        return service.authorize(
            source_id,
            policy_snapshot=current_snapshot,
            policy_mode="current",
            policy_id=current_policy_id,
        )

    print(f"Policy update for {source.display_name}:")
    policy_diff_lines = _policy_diff_lines(authorization.policy_snapshot, current_snapshot)
    if policy_diff_lines:
        for line in policy_diff_lines:
            print(line)
    else:
        print("-   <no diff in tracked policy fields>")
    escalation = _policy_escalation_detected(authorization.policy_snapshot, current_snapshot)
    if auto_approve and escalation:
        print("Auto-approve enabled: accepting expanded policy update.")
        return service.authorize(
            source_id,
            policy_snapshot=current_snapshot,
            policy_mode="current",
            policy_id=current_policy_id,
        )

    while True:
        selected = (
            input(
                "Proceed with policy update? [y/N] "
                "[1]=accept, [2]=keep legacy, [3]=cancel [default: N]: "
            )
            .strip()
            .lower()
        )
        if selected in {"", "n", "cancel", "q", "quit", "3"}:
            print("Authorization cancelled.")
            return None
        if selected in {"1", "y", "yes", "accept"}:
            if escalation:
                confirmation = input("Type 'accept log' to continue: ").strip()
                if confirmation != "accept log":
                    print("Authorization cancelled.")
                    return None
            return service.authorize(
                source_id,
                policy_snapshot=current_snapshot,
                policy_mode="current",
                policy_id=current_policy_id,
            )
        if selected == "2":
            return service.authorize(
                source_id,
                policy_snapshot=authorization.policy_snapshot,
                policy_mode="legacy",
            )
        if selected not in {"1", "2", "3", "y", "yes", "accept", "n", "cancel", "q", "quit"}:
            print("Invalid option. Use 1, 2, or 3.")
            continue


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Anamnesis local AI session discovery and search"
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=None,
        help="Anamnesis workspace directory; defaults to ~/.anamnesis.",
    )
    parser.add_argument(
        "--home",
        type=Path,
        default=None,
        help="Home directory override for discovery; mainly useful for tests.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("discover", help="Inventory known AI session sources")

    authorize = sub.add_parser("authorize", help="Authorize a discovered source")
    authorize.add_argument("source_id")
    authorize.add_argument(
        "--auto-approve",
        action="store_true",
        help="Automatically accept policy updates without interactive prompts.",
    )
    authorize.add_argument(
        "--yes",
        action="store_true",
        help="Alias for --auto-approve to support scripted non-interactive runs.",
    )

    revoke = sub.add_parser("revoke", help="Revoke and purge a source")
    revoke.add_argument("source_id")

    sub.add_parser("index", help="Index all authorized sources")

    privacy_audit = sub.add_parser(
        "privacy-audit", help="Audit local Anamnesis privacy posture"
    )
    privacy_audit.add_argument(
        "--fix-permissions",
        action="store_true",
        help="Repair workspace/database/authorization file modes without reading content.",
    )
    privacy_audit.add_argument(
        "--generate-report",
        action="store_true",
        help="Print a privacy-safe diagnostic summary for issue sharing.",
    )

    sub.add_parser("debug-report", help="Generate an anonymized local diagnostics report")

    search = sub.add_parser("search", help="Search the local index")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=10)
    search.add_argument(
        "--verbose",
        action="store_true",
        help="Include indexing diagnostics with search output.",
    )

    sub.add_parser("status", help="Show per-source indexing health")

    sub.add_parser("versions", help="Show version information")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    service = AnamnesisService(workspace_root=args.workspace, home=args.home)

    try:
        if args.command == "discover":
            sources = service.discover()
            _print_json(
                {
                    "sources": sources,
                    **_build_discover_tour(sources),
                }
            )
            return 0

        if args.command == "authorize":
            authorization = _prompt_authorize_with_policy_review(
                service,
                args.source_id,
                auto_approve=args.auto_approve or args.yes,
            )
            if authorization is None:
                return 2
            _print_json({"authorization": authorization})
            return 0

        if args.command == "revoke":
            purged_chunks = service.revoke(args.source_id)
            _print_json({"source_id": args.source_id, "purged_chunks": purged_chunks})
            return 0

        if args.command == "index":
            _print_json(service.index_authorized_sources())
            return 0

        if args.command == "privacy-audit":
            if args.generate_report:
                _print_json(service.debug_report())
                return 0
            _print_json(service.privacy_audit(fix_permissions=args.fix_permissions))
            return 0

        if args.command == "debug-report":
            _print_json(service.debug_report())
            return 0

        if args.command == "search":
            results = service.search(args.query, limit=args.limit)
            status_payload = service.status()
            enriched_results = _enrich_search_results(
                results,
                source_status_rows=status_payload["sources"],
            )
            health = service.sync_health()
            if args.verbose:
                _print_json(
                    {
                        "results": enriched_results,
                        "index_health": health,
                    }
                )
            else:
                if health["has_issues"]:
                    issue_count = len(health["issues"])
                    print(
                        f"[!] Sync notice: {issue_count} source"
                        f"{'s' if issue_count != 1 else ''} went silent. "
                        "Run 'anamnesis status' for details."
                    )
                _print_json({"results": enriched_results})
            return 0

        if args.command == "status":
            _print_json(service.status())
            return 0

        if args.command == "versions":
            _print_json(
                {
                    "app": "anamnesis",
                    "service_version": __version__,
                    "python_version": platform.python_version(),
                    "python_executable": sys.executable,
                }
            )
            return 0

    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except AnamnesisSearchError as exc:
        _print_json({"error": {"code": "invalid_search_query", "message": str(exc)}}, file=sys.stderr)
        return 2

    parser.error(f"unknown command: {args.command}")
    return 2
