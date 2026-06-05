from __future__ import annotations

from pathlib import Path

from anamnesis.models import ParsedSessionFile
from anamnesis.parser_adapters import adapters, get_adapter
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
