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
from .service import AnamnesisService


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
            _print_json({"authorization": service.authorize(args.source_id)})
            return 0

        if args.command == "revoke":
            purged_chunks = service.revoke(args.source_id)
            _print_json({"source_id": args.source_id, "purged_chunks": purged_chunks})
            return 0

        if args.command == "index":
            _print_json(service.index_authorized_sources())
            return 0

        if args.command == "privacy-audit":
            _print_json(
                service.privacy_audit(fix_permissions=args.fix_permissions)
            )
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
