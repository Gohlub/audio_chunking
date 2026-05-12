"""
Normalize arbitrary audio (WAV / MP3 / etc.) to **16 kHz mono FLAC** via FFmpeg.

This is the only audio transformation that runs during dataset preparation. The resulting FLAC
file is the source-of-truth for every downstream step (chunking, transcription, evaluation).

FLAC is chosen for lossless compression.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

TARGET_SR_HZ = 16_000
TARGET_CHANNELS = 1


def require_ffmpeg() -> None:
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg is not on PATH; install ffmpeg to prepare datasets.")
    if not shutil.which("ffprobe"):
        raise SystemExit("ffprobe is not on PATH; install ffmpeg (ships with ffprobe) to prepare datasets.")


def normalize_to_flac(
    src: Path,
    dst: Path,
    *,
    sample_rate_hz: int = TARGET_SR_HZ,
    mono: bool = True,
    flac_compression_level: int = 5,
) -> Path:
    """
    Decode ``src`` (any FFmpeg-readable format), resample to ``sample_rate_hz``, downmix to mono
    if requested, and write FLAC to ``dst``. Returns the resolved ``dst`` path.
    """
    src = Path(src).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(src)
    require_ffmpeg()

    dst = Path(dst).expanduser().resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)

    cmd: list[str] = [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(src),
        "-ac",
        "1" if mono else "2",
        "-ar",
        str(sample_rate_hz),
        "-c:a",
        "flac",
        "-compression_level",
        str(flac_compression_level),
        str(dst),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return dst


def ffprobe_duration_seconds(path: Path) -> float:
    """Return the duration of an audio file in seconds (uses ``ffprobe``)."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(json.loads(result.stdout)["format"]["duration"])
