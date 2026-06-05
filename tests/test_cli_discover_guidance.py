from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_discover(home: Path) -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, "-m", "anamnesis", "discover", "--home", str(home)],
        capture_output=True,
        cwd=REPO_ROOT,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert completed.stderr == ""
    return json.loads(completed.stdout)


def test_discover_includes_manual_import_tour(tmp_path: Path) -> None:
    home = tmp_path / "home"
    payload = _run_discover(home)
    manual_import_paths = {
        item["source_type"]: item
        for item in payload["manual_import_paths"]  # type: ignore[union-attr]
    }
    assert manual_import_paths["claude"]["path"] == str(home / "Anamnesis" / "imports" / "claude")
    assert manual_import_paths["chatgpt_export"]["path"] == str(
        home / "Anamnesis" / "chatgpt_exports"
    )
    assert manual_import_paths["gemini_export"]["path"] == str(
        home / "Anamnesis" / "imports" / "gemini"
    )
    assert manual_import_paths["character_ai_export"]["path"] == str(
        home / "Anamnesis" / "imports" / "character_ai"
    )
    assert manual_import_paths["notion_export"]["path"] == str(
        home / "Anamnesis" / "imports" / "notion"
    )

    first_run_tour = payload["first_run_tour"]  # type: ignore[assignment]
    assert len(first_run_tour) >= 3  # type: ignore[arg-type]
    assert "copy exports into path" in first_run_tour[1]  # type: ignore[index]
