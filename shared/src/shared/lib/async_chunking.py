"""
Async time-window chunking with FFmpeg/ffprobe.

Each chunk is written as **16 kHz mono FLAC**. Optional **EBU R128 loudnorm** runs per slice so
levels are consistent for downstream STT.

Dataset-specific FLAC slicing lives in benchmark ``lib.chunking``; this module targets generic
audio paths (e.g. the CocoIndex pipeline).
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ChunkingConfig:
    strategy: str = "hybrid"
    chunk_seconds: float = 600.0
    overlap_seconds: float = 5.0
    max_direct_bytes: int = 25_000_000
    max_direct_seconds: float = 18 * 60.0
    hybrid_silence_min_duration: float = 10.0
    hybrid_vad_threshold: float = 0.5
    hybrid_vad_sample_rate: int = 16_000
    silence_threshold_db: float = -35.0
    silence_min_duration: float = 0.5
    min_chunk_seconds: float = 0.2
    flac_compression_level: int = 5
    normalize_audio: bool = True


async def chunk_audio(
    audio_path: pathlib.Path,
    output_dir: pathlib.Path,
    config: ChunkingConfig,
) -> list[pathlib.Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    duration = await probe_audio_duration(audio_path)
    if duration <= 0:
        return []

    strategy = config.strategy.lower()
    if strategy == "hybrid":
        return await _hybrid_chunks(audio_path, output_dir, duration, config)
    if strategy == "overlap":
        ranges = _overlap_ranges(
            duration,
            config.chunk_seconds,
            config.overlap_seconds,
            config.min_chunk_seconds,
        )
    elif strategy == "silence":
        ranges = await _silence_ranges(audio_path, duration, config)
    else:
        raise ValueError(
            f"unsupported chunking strategy: {config.strategy} "
            "(supported: hybrid, overlap, silence; use overlap with overlap_seconds=0 "
            "for contiguous windows)"
        )

    return await _extract_ranges(audio_path, output_dir, ranges, config)


async def _hybrid_chunks(
    audio_path: pathlib.Path,
    output_dir: pathlib.Path,
    duration: float,
    config: ChunkingConfig,
) -> list[pathlib.Path]:
    full_flac = await _prepare_hybrid_source(audio_path, output_dir, duration, config)
    speech_ranges = await _detect_vad_speech_ranges(full_flac, duration, config)
    if not speech_ranges:
        return []

    if _within_direct_limits(full_flac, duration, config):
        return [full_flac]

    silences = _silence_ranges_from_speech(
        speech_ranges,
        duration,
        config.hybrid_silence_min_duration,
    )
    ranges = _hybrid_ranges(
        duration,
        silences,
        config.chunk_seconds,
        config.min_chunk_seconds,
    )
    return await _extract_ranges(
        full_flac,
        output_dir,
        ranges,
        config,
        normalize_audio=False,
    )


async def _prepare_hybrid_source(
    audio_path: pathlib.Path,
    output_dir: pathlib.Path,
    duration: float,
    config: ChunkingConfig,
) -> pathlib.Path:
    if not config.normalize_audio and await _is_compatible_flac(audio_path):
        return audio_path

    full_flac = output_dir / f"{audio_path.stem}.flac"
    await extract_audio_slice(
        audio_path,
        full_flac,
        0.0,
        duration,
        flac_compression_level=config.flac_compression_level,
        normalize_audio=config.normalize_audio,
    )
    return full_flac


def _within_direct_limits(
    audio_path: pathlib.Path,
    duration: float,
    config: ChunkingConfig,
) -> bool:
    return (
        duration < config.max_direct_seconds
        and audio_path.stat().st_size < config.max_direct_bytes
    )


async def _extract_ranges(
    audio_path: pathlib.Path,
    output_dir: pathlib.Path,
    ranges: list[tuple[float, float]],
    config: ChunkingConfig,
    *,
    normalize_audio: bool | None = None,
) -> list[pathlib.Path]:
    chunks: list[pathlib.Path] = []
    for idx, (start, end) in enumerate(ranges):
        out = output_dir / f"{audio_path.stem}.chunk{idx:04d}.flac"
        await extract_audio_slice(
            audio_path,
            out,
            start,
            end - start,
            flac_compression_level=config.flac_compression_level,
            normalize_audio=(
                config.normalize_audio if normalize_audio is None else normalize_audio
            ),
        )
        chunks.append(out)
    return chunks


async def probe_audio_duration(audio_path: pathlib.Path) -> float:
    proc = await asyncio.create_subprocess_exec(
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffprobe failed for {audio_path}: {stderr.decode(errors='replace').strip()}"
        )
    return float(stdout.decode().strip() or 0.0)


async def _is_compatible_flac(audio_path: pathlib.Path) -> bool:
    proc = await asyncio.create_subprocess_exec(
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_name,sample_rate,channels",
        "-of",
        "json",
        str(audio_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffprobe failed for {audio_path}: {stderr.decode(errors='replace').strip()}"
        )
    streams = json.loads(stdout.decode() or "{}").get("streams", [])
    if not streams:
        return False
    stream = streams[0]
    return (
        stream.get("codec_name") == "flac"
        and int(stream.get("sample_rate", 0)) == 16_000
        and int(stream.get("channels", 0)) == 1
    )


async def extract_audio_slice(
    input_path: pathlib.Path,
    output_path: pathlib.Path,
    start: float,
    duration: float,
    *,
    flac_compression_level: int = 5,
    normalize_audio: bool = True,
) -> None:
    cmd: list[str] = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{start:.3f}",
        "-t",
        f"{duration:.3f}",
        "-i",
        str(input_path),
        "-vn",
    ]
    if normalize_audio:
        cmd.extend(["-af", "loudnorm=I=-16:TP=-1.5:LRA=11"])
    cmd.extend(
        [
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "flac",
            "-compression_level",
            str(flac_compression_level),
            str(output_path),
        ]
    )
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg slice failed for {input_path}: {stderr.decode(errors='replace').strip()}"
        )


def _overlap_ranges(
    total_duration: float,
    chunk_seconds: float,
    overlap_seconds: float,
    min_chunk_seconds: float,
) -> list[tuple[float, float]]:
    if chunk_seconds <= 0:
        raise ValueError("chunk_seconds must be > 0")
    step = chunk_seconds - overlap_seconds
    if step <= 0:
        raise ValueError("overlap_seconds must be < chunk_seconds")

    ranges: list[tuple[float, float]] = []
    start = 0.0
    while start < total_duration:
        end = min(total_duration, start + chunk_seconds)
        if end - start >= min_chunk_seconds:
            ranges.append((start, end))
        start += step
    return ranges


def _hybrid_ranges(
    total_duration: float,
    silence_ranges: list[tuple[float, float]],
    max_chunk_seconds: float,
    min_chunk_seconds: float,
) -> list[tuple[float, float]]:
    if max_chunk_seconds <= 0:
        raise ValueError("chunk_seconds must be > 0")

    boundaries = sorted(
        (start + end) / 2
        for start, end in silence_ranges
        if 0 < start < end < total_duration
    )
    ranges: list[tuple[float, float]] = []
    start = 0.0
    while start < total_duration:
        max_end = min(total_duration, start + max_chunk_seconds)
        end = max_end
        if max_end < total_duration:
            candidates = [
                boundary
                for boundary in boundaries
                if start + min_chunk_seconds <= boundary <= max_end
            ]
            if candidates:
                end = candidates[-1]
        if end - start >= min_chunk_seconds:
            ranges.append((start, end))
        start = end
    return ranges


async def _detect_vad_speech_ranges(
    audio_path: pathlib.Path,
    total_duration: float,
    config: ChunkingConfig,
) -> list[tuple[float, float]]:
    def _run() -> list[dict[str, float]]:
        from .vad import speech_segments

        return speech_segments(
            audio_path,
            threshold=config.hybrid_vad_threshold,
            sampling_rate=config.hybrid_vad_sample_rate,
        )

    speech = await asyncio.to_thread(_run)
    return [
        (max(0.0, segment["start"]), min(total_duration, segment["end"]))
        for segment in speech
        if segment["end"] > segment["start"]
    ]


def _silence_ranges_from_speech(
    speech_ranges: list[tuple[float, float]],
    total_duration: float,
    min_silence_duration: float,
) -> list[tuple[float, float]]:
    silences: list[tuple[float, float]] = []
    cursor = 0.0
    for speech_start, speech_end in sorted(speech_ranges):
        if speech_start - cursor >= min_silence_duration:
            silences.append((cursor, speech_start))
        cursor = max(cursor, speech_end)
    if total_duration - cursor >= min_silence_duration:
        silences.append((cursor, total_duration))
    return silences


async def _silence_ranges(
    audio_path: pathlib.Path,
    total_duration: float,
    config: ChunkingConfig,
) -> list[tuple[float, float]]:
    silences = await _detect_silence_segments(
        audio_path,
        config.silence_threshold_db,
        config.silence_min_duration,
    )
    speech_ranges = _speech_ranges_from_silence(silences, total_duration)
    if config.chunk_seconds > 0:
        return _split_long_ranges(speech_ranges, config.chunk_seconds, config.min_chunk_seconds)
    return [r for r in speech_ranges if r[1] - r[0] >= config.min_chunk_seconds]


async def _detect_silence_segments(
    audio_path: pathlib.Path,
    silence_threshold_db: float,
    silence_min_duration: float,
) -> list[tuple[float, float]]:
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-hide_banner",
        "-i",
        str(audio_path),
        "-af",
        f"silencedetect=n={silence_threshold_db}dB:d={silence_min_duration}",
        "-f",
        "null",
        "-",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    log = stderr.decode(errors="replace")
    starts = [float(x) for x in re.findall(r"silence_start: ([0-9.]+)", log)]
    ends = [float(x) for x in re.findall(r"silence_end: ([0-9.]+)", log)]
    if not starts or not ends:
        return []
    pairs: list[tuple[float, float]] = []
    for start, end in zip(starts, ends):
        if end > start:
            pairs.append((start, end))
    return pairs


def _speech_ranges_from_silence(
    silence_ranges: list[tuple[float, float]],
    total_duration: float,
) -> list[tuple[float, float]]:
    if not silence_ranges:
        return [(0.0, total_duration)]

    speech: list[tuple[float, float]] = []
    cursor = 0.0
    for sil_start, sil_end in silence_ranges:
        if sil_start > cursor:
            speech.append((cursor, sil_start))
        cursor = max(cursor, sil_end)
    if cursor < total_duration:
        speech.append((cursor, total_duration))
    return speech


def _split_long_ranges(
    ranges: list[tuple[float, float]],
    max_seconds: float,
    min_chunk_seconds: float,
) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for start, end in ranges:
        cursor = start
        while cursor < end:
            chunk_end = min(end, cursor + max_seconds)
            if chunk_end - cursor >= min_chunk_seconds:
                out.append((cursor, chunk_end))
            cursor += max_seconds
    return out
