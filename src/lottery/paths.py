from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    return repo_root() / "data"


def processed_dir() -> Path:
    return data_dir() / "processed"


def history_dir() -> Path:
    return repo_root() / "history"


def manifest_path() -> Path:
    return processed_dir() / "manifest.json"


def schema_path() -> Path:
    return processed_dir() / "schema.json"
