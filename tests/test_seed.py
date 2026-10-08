"""Seed loader: data/*.txt -> registry."""

from pathlib import Path

from ingest.seed import load_seeds


def test_seeds_load():
    root = Path(__file__).resolve().parent.parent
    reg = load_seeds(root / "data")
    assert "bnss_2023" in reg.docs
    assert len(reg.chunks) >= 3


def test_missing_dir_empty(tmp_path):
    reg = load_seeds(tmp_path / "nodir")
    assert reg.docs == {}
