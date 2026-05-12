"""
Shared building blocks used by every dataset's ``prepare`` script and by the dataset-agnostic
pipeline stages (``lib.chunking``, ``lib.transcription``).

Submodules (each readable on its own):

  paths          - filesystem layout (raw_audio_dir, chunked_audio_dir, …)
  fetching       - HTTP download + zip-extraction helpers
  normalization  - FFmpeg -> 16 kHz mono FLAC (+ ffprobe duration)
  cases          - BenchmarkCase, hypothesis_is_placeholder, write_benchmark_cases (.ref / .hyp)
  word_xml       - shared NITE NXT word-XML parser (used by AMI and ICSI)

The names re-exported below are the ones consumers reach for; deeper helpers live under each
submodule (e.g. ``from datasets.prepare.word_xml import Word``).
"""
from __future__ import annotations

from datasets.prepare.cases import (
    BenchmarkCase,
    collapse_comma_runs,
    hypothesis_is_placeholder,
    write_benchmark_cases,
)
from datasets.prepare.fetching import (
    download_file,
    ensure_words_layer,
    has_word_layer,
    require_option,
)
from datasets.prepare.normalization import (
    TARGET_CHANNELS,
    TARGET_SR_HZ,
    ffprobe_duration_seconds,
    normalize_to_flac,
    require_ffmpeg,
)
from datasets.prepare.paths import (
    benchmark_hypotheses_dir,
    benchmark_references_dir,
    benchmark_root,
    cache_dir,
    chunked_audio_dir,
    dataset_root,
    licence_path,
    prepared_root,
    raw_audio_dir,
    raw_audio_path,
    scripts_root,
)
from datasets.prepare.word_xml import reference_text_for_meeting

__all__ = [
    # cases
    "BenchmarkCase",
    "write_benchmark_cases",
    "collapse_comma_runs",
    "hypothesis_is_placeholder",
    # fetching
    "download_file",
    "ensure_words_layer",
    "has_word_layer",
    "require_option",
    # normalization
    "normalize_to_flac",
    "require_ffmpeg",
    "ffprobe_duration_seconds",
    "TARGET_SR_HZ",
    "TARGET_CHANNELS",
    # paths
    "scripts_root",
    "prepared_root",
    "dataset_root",
    "raw_audio_dir",
    "raw_audio_path",
    "chunked_audio_dir",
    "cache_dir",
    "benchmark_root",
    "benchmark_references_dir",
    "benchmark_hypotheses_dir",
    "licence_path",
    # word_xml
    "reference_text_for_meeting",
]
