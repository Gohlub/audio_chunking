"""
Filesystem layout for the benchmark.

Project root (``scripts_root``) is the directory that contains ``datasets/``, ``evaluation/``,
``data/``, and ``pyproject.toml``. Everything below lives under ``data/prepared/``.

Per-dataset layout:

    data/prepared/<dataset>/
        audio/raw/<case_id>.flac           # 16 kHz mono FLAC; written by ``datasets.<name>.prepare``
        audio/chunked/<case_id>/part*.{flac|wav|mp3} # overlapping chunks; format from ``--chunk-format`` / ``BENCHMARK_CHUNK_FORMAT``
        cache/                             # transient downloads (deleted by prepare on success)

Cross-dataset transcript outputs (consumed by ``evaluation/``):

    data/prepared/benchmark/references/<case_id>.ref.txt
    data/prepared/benchmark/hypotheses/<case_id>.hyp.txt
    data/prepared/licence/CCBY4.0.txt
"""
from __future__ import annotations

from pathlib import Path


def scripts_root() -> Path:
    # benchmark/datasets/prepare/paths.py -> three .parents land at benchmark/
    return Path(__file__).resolve().parent.parent.parent


def prepared_root() -> Path:
    return scripts_root() / "data" / "prepared"


def dataset_root(dataset: str) -> Path:
    return prepared_root() / dataset


def raw_audio_dir(dataset: str) -> Path:
    """FLAC source-of-truth for the dataset (one ``<case_id>.flac`` per case)."""
    return dataset_root(dataset) / "audio" / "raw"


def chunked_audio_dir(dataset: str) -> Path:
    """Per-case chunk directories written by :mod:`lib.chunking` (``part*.flac``, ``part*.wav``, or ``part*.mp3``)."""
    return dataset_root(dataset) / "audio" / "chunked"


def cache_dir(dataset: str) -> Path:
    """Transient downloads (zip files, source MP3s). Safe to delete."""
    return dataset_root(dataset) / "cache"


def benchmark_root() -> Path:
    return prepared_root() / "benchmark"


def benchmark_references_dir() -> Path:
    return benchmark_root() / "references"


def benchmark_hypotheses_dir() -> Path:
    return benchmark_root() / "hypotheses"


def licence_path() -> Path:
    return prepared_root() / "licence" / "CCBY4.0.txt"


def raw_audio_path(dataset: str, case_id: str) -> Path:
    return raw_audio_dir(dataset) / f"{case_id}.flac"
