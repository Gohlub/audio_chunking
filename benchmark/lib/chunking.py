"""
Slice prepared FLAC into overlapping parts under ``audio/chunked/<case_id>/``.

Input:   ``data/prepared/<dataset>/audio/raw/<case_id>.flac``  (16 kHz mono, from ``datasets.<name>.prepare``)
Output:  ``data/prepared/<dataset>/audio/chunked/<case_id>/part0001.{flac|wav|mp3}`` …

Parts cover the source FLAC with ``chunk_seconds`` length and ``overlap_seconds`` shared between
adjacent parts. Sorted lexicographically, the parts are in time order; :mod:`lib.transcription`
consumes them in that order and merges with longest-common-sequence alignment (no timestamps required).

"""
from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from datasets.prepare import (
    chunked_audio_dir,
    ffprobe_duration_seconds,
    raw_audio_path,
    require_ffmpeg,
)

ChunkFormat = Literal["flac", "wav", "mp3"]

# Mono MP3 bitrate for ``chunk_format=mp3`` (override with env ``BENCHMARK_CHUNK_MP3_BITRATE``, e.g. ``96k``).
def _mp3_bitrate() -> str:
    b = os.environ.get("BENCHMARK_CHUNK_MP3_BITRATE", "128k").strip()
    return b or "128k"


def parse_chunk_format(s: str) -> ChunkFormat:
    v = s.strip().lower()
    if v not in ("flac", "wav", "mp3"):
        raise ValueError(f"chunk_format must be flac, wav, or mp3, got {s!r}")
    return v  # type: ignore[return-value]


def chunk_suffix(chunk_format: str) -> str:
    f = parse_chunk_format(chunk_format)
    return { "flac": ".flac", "wav": ".wav", "mp3": ".mp3" }[f]


def chunk_glob(chunk_format: str) -> str:
    return f"part*{chunk_suffix(chunk_format)}"


@dataclass(frozen=True)
class ChunkPlan:
    """One on-disk chunk: ``part_index`` (1-based) plus the time window in the source FLAC."""

    part_index: int
    start_seconds: float
    duration_seconds: float
    path: Path


def _validate(chunk_seconds: float, overlap_seconds: float) -> None:
    if chunk_seconds <= 0:
        raise ValueError(f"chunk_seconds must be > 0 (got {chunk_seconds})")
    if overlap_seconds < 0:
        raise ValueError(f"overlap_seconds must be >= 0 (got {overlap_seconds})")
    if overlap_seconds >= chunk_seconds:
        raise ValueError(
            f"overlap_seconds must be < chunk_seconds "
            f"(got overlap={overlap_seconds}, chunk={chunk_seconds})"
        )


def _plan(
    duration: float,
    chunk_seconds: float,
    overlap_seconds: float,
    *,
    out_dir: Path,
    ext: str,
) -> list[ChunkPlan]:
    """Compute the on-disk part layout. One part per (start, duration) window."""
    stride = chunk_seconds - overlap_seconds
    plans: list[ChunkPlan] = []
    pos = 0.0
    part = 0
    while pos < duration:
        part += 1
        remaining = duration - pos
        length = min(chunk_seconds, remaining)
        plans.append(
            ChunkPlan(
                part_index=part,
                start_seconds=pos,
                duration_seconds=length,
                path=out_dir / f"part{part:04d}{ext}",
            )
        )
        if length >= remaining - 1e-9:
            break
        pos += stride
    return plans


def _write_chunk(
    src: Path,
    plan: ChunkPlan,
    *,
    chunk_format: ChunkFormat,
    flac_compression_level: int = 5,
) -> None:
    """Re-encode the selected window from ``src`` into ``plan.path`` (16 kHz mono)."""
    plan.path.parent.mkdir(parents=True, exist_ok=True)
    if chunk_format == "flac":
        cmd: list[str] = [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            str(plan.start_seconds),
            "-i",
            str(src),
            "-t",
            str(plan.duration_seconds),
            "-c:a",
            "flac",
            "-compression_level",
            str(flac_compression_level),
            str(plan.path),
        ]
    elif chunk_format == "wav":
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            str(plan.start_seconds),
            "-i",
            str(src),
            "-t",
            str(plan.duration_seconds),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-f",
            "wav",
            "-acodec",
            "pcm_s16le",
            str(plan.path),
        ]
    else:
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            str(plan.start_seconds),
            "-i",
            str(src),
            "-t",
            str(plan.duration_seconds),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "libmp3lame",
            "-b:a",
            _mp3_bitrate(),
            str(plan.path),
        ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def chunk_case(
    dataset: str,
    case_id: str,
    *,
    chunk_seconds: float,
    overlap_seconds: float,
    chunk_format: str = "mp3",
    force: bool = False,
) -> list[Path]:
    """
    Chunk ``data/prepared/<dataset>/audio/raw/<case_id>.flac`` into overlapping parts
    (codec per ``chunk_format``: flac, wav, or mp3).

    Returns the list of part paths in time order. Re-uses an existing chunked dir unless
    ``force=True`` (in which case the dir is wiped first).
    """
    fmt = parse_chunk_format(chunk_format)
    ext = chunk_suffix(fmt)
    _validate(chunk_seconds, overlap_seconds)
    require_ffmpeg()

    src = raw_audio_path(dataset, case_id)
    if not src.is_file():
        raise FileNotFoundError(
            f"raw FLAC missing for {dataset}/{case_id}: {src} "
            f"(run ``data/prepare_dataset.py {dataset}``)"
        )

    out_dir = chunked_audio_dir(dataset) / case_id
    if force and out_dir.exists():
        shutil.rmtree(out_dir)

    duration = ffprobe_duration_seconds(src)
    if duration <= 0:
        raise SystemExit(f"empty audio for {dataset}/{case_id}: {src}")

    plans = _plan(duration, chunk_seconds, overlap_seconds, out_dir=out_dir, ext=ext)

    pattern = chunk_glob(fmt)
    existing = sorted(out_dir.glob(pattern)) if out_dir.is_dir() else []
    if not force and len(existing) == len(plans) and all(p.path.is_file() for p in plans):
        print(
            f"[chunk] {dataset}/{case_id}: reuse {len(plans)} parts in {out_dir}",
            flush=True,
        )
        return [p.path for p in plans]

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(
        f"[chunk] {dataset}/{case_id}: {duration:.1f}s -> {len(plans)} parts "
        f"(chunk={chunk_seconds}s, overlap={overlap_seconds}s, format={fmt}) -> {out_dir}",
        flush=True,
    )
    for p in plans:
        _write_chunk(src, p, chunk_format=fmt)
    return [p.path for p in plans]


def chunk_dataset(
    dataset: str,
    case_ids: Sequence[str],
    *,
    chunk_seconds: float,
    overlap_seconds: float,
    chunk_format: str = "mp3",
    force: bool = False,
) -> dict[str, list[Path]]:
    """Run :func:`chunk_case` for each id; returns ``{case_id: [chunk_paths…]}``."""
    return {
        case_id: chunk_case(
            dataset,
            case_id,
            chunk_seconds=chunk_seconds,
            overlap_seconds=overlap_seconds,
            chunk_format=chunk_format,
            force=force,
        )
        for case_id in case_ids
    }
