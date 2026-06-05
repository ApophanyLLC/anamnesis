from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Callable, Iterator

from anamnesis.cli import _prompt_authorize_with_policy_review
from anamnesis.cli import definitions_by_source_type
from anamnesis.service import AnamnesisService


def _input_sequence(responses: list[str]) -> Callable[[str], str]:
    iterator: Iterator[str] = iter(responses)

    def _reader(_prompt: str = "") -> str:
        return next(iterator)

    return _reader


def test_authorization_manifest_persists_policy_snapshot(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source_root = home / ".codex" / "sessions"
    source_root.mkdir(parents=True)
    (source_root / "session.json").write_text(
        json.dumps(
            {
                "id": "snapshot-policy-session",
                "messages": [{"role": "user", "content": "policy visibility"}],
            }
        ),
        encoding="utf-8",
    )

    service = AnamnesisService(workspace_root=tmp_path / "workspace", home=home)
    codex = next(source for source in service.discover() if source.source_type == "codex")
    service.authorize(codex.source_id)

    manifest = json.loads((service.workspace_root / "sources.authorization.json").read_text())
    authorization_entry = manifest["sources"][0]
    snapshot = authorization_entry.get("policy_snapshot")
    assert isinstance(snapshot, dict)
    assert snapshot["source_type"] == "codex"
    assert snapshot["accepted_file_shapes"]


def test_authorize_requires_interactive_accept_log_for_escalation(
    tmp_path: Path, monkeypatch
) -> None:
    home = tmp_path / "home"
    source_root = home / ".codex" / "sessions"
    source_root.mkdir(parents=True)
    (source_root / "session.json").write_text(
        json.dumps(
            {
                "id": "escalation-session",
                "messages": [{"role": "user", "content": "escalation content"}],
            }
        ),
        encoding="utf-8",
    )

    service = AnamnesisService(workspace_root=tmp_path / "workspace", home=home)
    codex = next(source for source in service.discover() if source.source_type == "codex")
    service.authorize(codex.source_id)

    base_definitions = definitions_by_source_type()
    codex_definition = base_definitions[codex.source_type]
    escalated_definition = replace(
        codex_definition,
        risk_level="high",
        definition_id="",
    )

    monkeypatch.setattr(
        "anamnesis.cli.definitions_by_source_type",
        lambda: {
            **base_definitions,
            codex.source_type: escalated_definition,
        },
    )
    monkeypatch.setattr("builtins.input", _input_sequence(["1", "accept log"]))

    authorization = _prompt_authorize_with_policy_review(
        service, codex.source_id, auto_approve=False
    )
    assert authorization is not None
    assert authorization.policy_snapshot["risk_level"] == "high"
    assert authorization.policy_mode == "current"


def test_authorize_can_keep_legacy_mode_on_escalation(
    tmp_path: Path, monkeypatch
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

    service = AnamnesisService(workspace_root=tmp_path / "workspace", home=home)
    codex = next(source for source in service.discover() if source.source_type == "codex")
    service.authorize(codex.source_id)

    definitions = definitions_by_source_type()
    codex_definition = definitions[codex.source_type]
    original_snapshot = {
        "source_type": codex_definition.source_type,
        "accepted_file_shapes": list(codex_definition.accepted_file_shapes),
        "risk_level": codex_definition.risk_level,
    }
    escalated_definition = replace(
        codex_definition,
        accepted_file_shapes=("json", "jsonl", "md"),
        definition_id="",
    )
    monkeypatch.setattr(
        "anamnesis.cli.definitions_by_source_type",
        lambda: {
            **definitions,
            codex.source_type: escalated_definition,
        },
    )
    monkeypatch.setattr("builtins.input", _input_sequence(["2"]))

    authorization = _prompt_authorize_with_policy_review(
        service, codex.source_id, auto_approve=False
    )
    assert authorization is not None
    assert authorization.policy_mode == "legacy"
    assert authorization.policy_snapshot["accepted_file_shapes"] == list(
        original_snapshot["accepted_file_shapes"]
    )
