#!/usr/bin/env python3
"""
AMI prepare: download Mix-Headset audio, normalize to FLAC, parse manual word XML, write
benchmark reference transcripts.

Outputs:
  data/prepared/ami/audio/raw/<meeting>.flac
  data/prepared/benchmark/references/<meeting>.ref.txt
  data/prepared/benchmark/hypotheses/<meeting>.hyp.txt   (placeholder if missing)

Source WAVs and the annotation zip live in ``data/prepared/ami/cache/`` for the lifetime of the
prepare run and are wiped on success.
"""
from __future__ import annotations

import argparse
import shutil
from collections.abc import Sequence
from pathlib import Path

from datasets.prepare import (
    cache_dir,
    download_file,
    ensure_words_layer,
    licence_path,
    normalize_to_flac,
    raw_audio_dir,
    raw_audio_path,
    require_ffmpeg,
    write_benchmark_cases,
)

from .transcripts import build_cases

DEFAULT_MEETINGS = ("EN2001a", "ES2008a", "ES2008b")
DATASET = "ami"

AUDIO_MIRROR = "https://groups.inf.ed.ac.uk/ami/AMICorpusMirror//amicorpus"
ANNOT_ZIP_URL = (
    "https://groups.inf.ed.ac.uk/ami/AMICorpusAnnotations/ami_public_manual_1.6.2.zip"
)
LICENSE_URL = "https://groups.inf.ed.ac.uk/ami/download/CCBY4.0.txt"
USER_AGENT = "STT-exploration-ami-fetch/1.0"
MANUAL_DIR_NAME = "ami_public_manual_1.6.2"


def _ensure_meeting_flac(meeting: str, *, force: bool, cache: Path) -> Path:
    """Download Mix-Headset WAV into ``cache``, encode to ``audio/raw/<meeting>.flac``."""
    flac = raw_audio_path(DATASET, meeting)
    if flac.is_file() and not force:
        print(f"skip (exists): {flac}", flush=True)
        return flac
    flac.parent.mkdir(parents=True, exist_ok=True)

    src = cache / f"{meeting}.Mix-Headset.wav"
    url = f"{AUDIO_MIRROR}/{meeting}/audio/{meeting}.Mix-Headset.wav"
    download_file(url, src, force=force, user_agent=USER_AGENT)

    print(f"  encode: {src.name} -> {flac.name}", flush=True)
    normalize_to_flac(src, flac)
    return flac


def _ensure_manual(*, force: bool, cache: Path) -> Path:
    return ensure_words_layer(
        cache,
        nested_dir_name=MANUAL_DIR_NAME,
        zip_name=f"{MANUAL_DIR_NAME}.zip",
        zip_url=ANNOT_ZIP_URL,
        force=force,
        user_agent=USER_AGENT,
    )


def prepare(meetings: Sequence[str], *, force: bool = False) -> int:
    require_ffmpeg()
    cache = cache_dir(DATASET).resolve()
    cache.mkdir(parents=True, exist_ok=True)
    raw_audio_dir(DATASET).mkdir(parents=True, exist_ok=True)

    licence = licence_path()
    licence.parent.mkdir(parents=True, exist_ok=True)
    download_file(LICENSE_URL, licence, force=force, user_agent=USER_AGENT)

    print(f"[ami] audio ({len(meetings)} meetings) -> {raw_audio_dir(DATASET)}", flush=True)
    for m in meetings:
        _ensure_meeting_flac(m, force=force, cache=cache)

    print("[ami] manual word XML …", flush=True)
    manual_dir = _ensure_manual(force=force, cache=cache)

    print("[ami] reference transcripts …", flush=True)
    write_benchmark_cases(build_cases(manual_dir, meetings))

    shutil.rmtree(cache, ignore_errors=True)
    print(f"[ami] done. flac: {raw_audio_dir(DATASET)} ; refs: see data/prepared/benchmark/")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "meetings",
        nargs="*",
        help=f"Meeting IDs (default: {' '.join(DEFAULT_MEETINGS)})",
    )
    p.add_argument(
        "--force-fetch",
        action="store_true",
        help="Re-download and re-encode even if outputs exist",
    )
    args = p.parse_args(list(argv) if argv is not None else None)
    meetings = list(args.meetings) if args.meetings else list(DEFAULT_MEETINGS)
    return prepare(meetings, force=args.force_fetch)


if __name__ == "__main__":
    raise SystemExit(main())
