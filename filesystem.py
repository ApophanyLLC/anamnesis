"""Filesystem permission helpers for Anamnesis private data."""

from __future__ import annotations

from pathlib import Path


PRIVATE_DIR_MODE = 0o700
PRIVATE_FILE_MODE = 0o600


def ensure_private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=PRIVATE_DIR_MODE)
    path.chmod(PRIVATE_DIR_MODE)


def ensure_private_file(path: Path) -> None:
    path.chmod(PRIVATE_FILE_MODE)


def file_mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


def format_mode(mode: int | None) -> str | None:
    return None if mode is None else f"{mode:03o}"
