#!/usr/bin/env python3
"""
ICSI prepare: download interaction audio, normalize to FLAC, parse manual word XML, write
benchmark reference transcripts.

Outputs:
  data/prepared/icsi/audio/raw/<meeting>.flac
  data/prepared/benchmark/references/<meeting>.ref.txt
  data/prepared/benchmark/hypotheses/<meeting>.hyp.txt   (placeholder if missing)

Source WAVs and the annotation zip live in ``data/prepared/icsi/cache/`` for the lifetime of the
prepare run and are wiped on success.
"""
from __future__ import annotations

import argparse
import os
import shutil
from collections.abc import Sequence
from pathlib import Path

from datasets.prepare import (
    cache_dir,
    download_file,
    ensure_words_layer,
    has_word_layer,
    licence_path,
    normalize_to_flac,
    raw_audio_dir,
    raw_audio_path,
    require_ffmpeg,
    write_benchmark_cases,
)

from .transcripts import build_cases

DEFAULT_MEETINGS = ("Bmr001", "Bns001", "Bro003")
DATASET = "icsi"

DEFAULT_AUDIO_MIRROR = "https://groups.inf.ed.ac.uk/ami/ICSIsignals/NXT"
DEFAULT_ANNOT_ZIP_URL = (
    "https://groups.inf.ed.ac.uk/ami/ICSICorpusAnnotations/ICSI_core_NXT.zip"
)
LICENSE_URL = "https://groups.inf.ed.ac.uk/ami/download/CCBY4.0.txt"
USER_AGENT = "STT-exploration-icsi-fetch/1.0"
MANUAL_DIR_NAME = "icsi_annotations"


def _ensure_meeting_flac(meeting: str, *, force: bool, mirror: str, cache: Path) -> Path:
    """Download interaction WAV into ``cache``, encode to ``audio/raw/<meeting>.flac``."""
    flac = raw_audio_path(DATASET, meeting)
    if flac.is_file() and not force:
        print(f"skip (exists): {flac}", flush=True)
        return flac
    flac.parent.mkdir(parents=True, exist_ok=True)

    src = cache / f"{meeting}.interaction.wav"
    url = f"{mirror.rstrip('/')}/{meeting}.interaction.wav"
    download_file(url, src, force=force, user_agent=USER_AGENT)

    print(f"  encode: {src.name} -> {flac.name}", flush=True)
    normalize_to_flac(src, flac)
    return flac


def _relayout_icsi_words(nested: Path) -> None:
    """``ICSI_core_NXT.zip`` unpacks to ``ICSI/Words/*.words.xml``; rename to ``words/``."""
    if has_word_layer(nested):
        return
    src = nested / "ICSI" / "Words"
    dst = nested / "words"
    if not src.is_dir() or not any(src.glob("*.words.xml")):
        return
    if dst.exists():
        shutil.rmtree(dst)
    src.rename(dst)


def _ensure_manual(*, force: bool, cache: Path, zip_url: str) -> Path:
    return ensure_words_layer(
        cache,
        nested_dir_name=MANUAL_DIR_NAME,
        zip_name=f"{MANUAL_DIR_NAME}.zip",
        zip_url=zip_url,
        force=force,
        user_agent=USER_AGENT,
        after_extract=_relayout_icsi_words,
    )


def prepare(
    meetings: Sequence[str],
    *,
    force: bool = False,
    audio_mirror: str | None = None,
    annot_zip_url: str | None = None,
) -> int:
    require_ffmpeg()
    cache = cache_dir(DATASET).resolve()
    cache.mkdir(parents=True, exist_ok=True)
    raw_audio_dir(DATASET).mkdir(parents=True, exist_ok=True)

    mirror = audio_mirror or os.environ.get("ICSI_AUDIO_MIRROR_URL", DEFAULT_AUDIO_MIRROR)
    zip_url = annot_zip_url or os.environ.get("ICSI_ANNOT_ZIP_URL", DEFAULT_ANNOT_ZIP_URL)

    licence = licence_path()
    licence.parent.mkdir(parents=True, exist_ok=True)
    download_file(LICENSE_URL, licence, force=force, user_agent=USER_AGENT)

    print(f"[icsi] audio ({len(meetings)} meetings) -> {raw_audio_dir(DATASET)}", flush=True)
    for m in meetings:
        _ensure_meeting_flac(m, force=force, mirror=mirror, cache=cache)

    print("[icsi] manual word XML …", flush=True)
    manual_dir = _ensure_manual(force=force, cache=cache, zip_url=zip_url)

    print("[icsi] reference transcripts …", flush=True)
    write_benchmark_cases(build_cases(manual_dir, meetings))

    shutil.rmtree(cache, ignore_errors=True)
    print(f"[icsi] done. flac: {raw_audio_dir(DATASET)} ; refs: see data/prepared/benchmark/")
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
    p.add_argument(
        "--audio-mirror",
        default=None,
        help=f"Override audio mirror (default env ICSI_AUDIO_MIRROR_URL or {DEFAULT_AUDIO_MIRROR})",
    )
    p.add_argument(
        "--annot-zip-url",
        default=None,
        help=f"Override annotations zip URL (default env ICSI_ANNOT_ZIP_URL or {DEFAULT_ANNOT_ZIP_URL})",
    )
    args = p.parse_args(list(argv) if argv is not None else None)
    meetings = list(args.meetings) if args.meetings else list(DEFAULT_MEETINGS)
    return prepare(
        meetings,
        force=args.force_fetch,
        audio_mirror=args.audio_mirror,
        annot_zip_url=args.annot_zip_url,
    )


if __name__ == "__main__":
    raise SystemExit(main())
