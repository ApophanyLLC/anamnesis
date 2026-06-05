from __future__ import annotations

import json
from pathlib import Path

import pytest

from anamnesis.models import ParsedSessionFile
from anamnesis import parser_documents
from anamnesis import session_schema
from anamnesis.parser_adapters import ParserAdapter, adapters, get_adapter
from anamnesis.registry import definitions_by_source_type


def test_active_parser_owners_are_registered_adapters() -> None:
    active_owners = {
        definition.parser_owner
        for definition in definitions_by_source_type().values()
        if definition.parser_owner != "unassigned"
    }
    registered_owners = {adapter.owner for adapter in adapters()}

    assert active_owners <= registered_owners


def test_adapters_expose_parser_contract(tmp_path: Path) -> None:
    sample_path = tmp_path / "sample.txt"
    sample_path.write_text("sample content", encoding="utf-8")

    for adapter in adapters():
        assert adapter.owner
        assert adapter.version
        assert callable(adapter.parse)
        assert adapter.fallback_parse is None or callable(adapter.fallback_parse)

        parsed = adapter.parse(
            sample_path,
            source_id="codex:test-source",
            source_type="codex",
        )
        assert isinstance(parsed, ParsedSessionFile)
        assert isinstance(parsed.documents, tuple)


def test_unknown_parser_owner_falls_back_to_unassigned(tmp_path: Path) -> None:
    assert get_adapter("parser_does_not_exist").owner == "unassigned"
    fallback = get_adapter("parser_does_not_exist")
    assert fallback.owner == "unassigned"
    assert fallback.version == "unassigned"

    sample_path = tmp_path / "sample.txt"
    sample_path.write_text("legacy fallback sample", encoding="utf-8")
    parsed = fallback.parse(
        sample_path,
        source_id="codex:test-source",
        source_type="codex",
    )
    assert isinstance(parsed, ParsedSessionFile)


def test_adapters_can_be_extended_by_external_modules(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_path = tmp_path / "external_adapter.py"
    module_path.write_text(
        """
from pathlib import Path

from anamnesis.models import ParsedSessionFile
from anamnesis.parser_adapters import ParserAdapter
from anamnesis.parser_documents import parse_text_document


def parse_external(path: Path, *, source_id: str, source_type: str) -> ParsedSessionFile:
    return parse_text_document(path, source_id=source_id, source_type=source_type)


def get_adapters() -> tuple[ParserAdapter, ...]:
    return (
        ParserAdapter(
            owner="parser_external",
            version="external/v1",
            parse=parse_external,
        ),
    )
""",
        encoding="utf-8",
    )

    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("ANAMNESIS_ADAPTER_MODULES", "external_adapter")

    loaded_adapters = adapters()
    assert any(adapter.owner == "parser_external" for adapter in loaded_adapters)
    assert isinstance(get_adapter("parser_external"), ParserAdapter)


def test_large_json_documents_use_streaming_parse_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = [{"id": f"session-{index}", "messages": [{"role": "user", "content": "x"}]} for index in range(3)]
    source_path = tmp_path / "large-session.json"
    source_path.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(parser_documents, "_JSON_STREAMING_THRESHOLD_BYTES", 1)

    def fail_read_text(*_: object, **__: object) -> str:
        raise AssertionError("legacy read_text path should not be used for streamed JSON")

    monkeypatch.setattr(Path, "read_text", fail_read_text, raising=False)

    parsed = parser_documents.parse_json_document(
        source_path,
        source_id="codex:test-source",
        source_type="codex",
    )
    assert parsed.parser_mode == "structured"
    assert len(parsed.documents) == 3


def test_standard_schema_round_trips_to_internal_documents(tmp_path: Path) -> None:
    payload = session_schema.StandardSession(
        session_id="session-1",
        source_id="codex:test-source",
        source_type="codex",
        title="Roundtrip",
        created_at="2026-01-01T00:00:00Z",
        modified_at="2026-01-01T00:10:00Z",
        exchanges=(
            session_schema.StandardExchange(
                timestamp="2026-01-01T00:00:00Z",
                role="user",
                content="hello",
            ),
        ),
        metadata={"source": "unit"},
    )

    document = session_schema.to_session_document(payload, path=tmp_path / "session.json")
    restored = session_schema.from_session_document(document)

    assert restored.session_id == payload.session_id
    assert restored.exchanges[0].content == payload.exchanges[0].content
