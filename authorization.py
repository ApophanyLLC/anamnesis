"""Persistent authorization manifest for Anamnesis sources."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

from .filesystem import ensure_private_directory, ensure_private_file
from .models import DiscoveredSource, SourceAuthorization


class AuthorizationStore:
    """Small JSON store that records explicit source authorization."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.authorizations = self._load()

    def authorize(self, source: DiscoveredSource) -> SourceAuthorization:
        authorization = SourceAuthorization(
            source_id=source.source_id,
            source_type=source.source_type,
            display_name=source.display_name,
            path=source.path,
            authorized=True,
            definition_id=source.definition_id,
        )
        self.authorizations[source.source_id] = authorization
        self._save()
        return authorization

    def revoke(self, source_id: str) -> SourceAuthorization | None:
        authorization = self.authorizations.get(source_id)
        if authorization is None:
            return None
        revoked = SourceAuthorization(
            source_id=authorization.source_id,
            source_type=authorization.source_type,
            display_name=authorization.display_name,
            path=authorization.path,
            authorized=False,
            definition_id=authorization.definition_id,
        )
        self.authorizations[source_id] = revoked
        self._save()
        return revoked

    def authorized_sources(self) -> tuple[SourceAuthorization, ...]:
        return tuple(
            sorted(
                (item for item in self.authorizations.values() if item.authorized),
                key=lambda item: item.source_id,
            )
        )

    def _load(self) -> dict[str, SourceAuthorization]:
        if not self.path.exists():
            return {}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        items = payload.get("sources", [])
        authorizations: dict[str, SourceAuthorization] = {}
        for item in items:
            authorization = SourceAuthorization(
                source_id=str(item["source_id"]),
                source_type=str(item["source_type"]),
                display_name=str(item["display_name"]),
                path=Path(str(item["path"])),
                authorized=bool(item["authorized"]),
                definition_id=str(item.get("definition_id") or ""),
            )
            authorizations[authorization.source_id] = authorization
        return authorizations

    def _save(self) -> None:
        ensure_private_directory(self.path.parent)
        payload = {
            "sources": [
                {
                    **asdict(item),
                    "path": str(item.path),
                }
                for item in sorted(
                    self.authorizations.values(), key=lambda value: value.source_id
                )
            ]
        }
        self.path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        ensure_private_file(self.path)
