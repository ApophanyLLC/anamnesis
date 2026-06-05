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
    SourceAuthorization,
    policy_id_for_snapshot,
    policy_snapshot_for_definition,
)
from .service import AnamnesisService
from .registry import definitions_by_source_type


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
    old_suffixes = sorted(str(value) for value in old.get("file_suffixes", ()))
    new_suffixes = sorted(str(value) for value in new.get("file_suffixes", ()))
    return len(set(new_suffixes) - set(old_suffixes)) > 0


def _prompt_authorize_with_policy_review(
    service: AnamnesisService, source_id: str
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
    if authorization.policy_id == current_policy_id and (
        authorization.policy_snapshot == current_snapshot
        or authorization.policy_mode != "legacy"
    ):
        return authorization

    print(f"Policy update for {source.display_name}:")
    for line in _policy_diff_lines(authorization.policy_snapshot, current_snapshot):
        print(line)
    escalation = _policy_escalation_detected(authorization.policy_snapshot, current_snapshot)
    while True:
        selected = (
            input(
                "Choose: [1] Accept new policy, [2] Keep legacy policy, "
                "[3] Cancel [default: 3]: "
            ).strip()
            or "3"
        )
        if selected == "3":
            print("Authorization cancelled.")
            return None
        if selected == "1":
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
        if selected not in {"1", "2", "3"}:
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
            _print_json({"sources": service.discover()})
            return 0

        if args.command == "authorize":
            authorization = _prompt_authorize_with_policy_review(service, args.source_id)
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
            health = service.sync_health()
            if args.verbose:
                _print_json({"results": results, "index_health": health})
            else:
                if health["has_issues"]:
                    issue_count = len(health["issues"])
                    print(
                        f"[!] Sync notice: {issue_count} source"
                        f"{'s' if issue_count != 1 else ''} went silent. "
                        "Run 'anamnesis status' for details."
                    )
                _print_json({"results": results})
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
