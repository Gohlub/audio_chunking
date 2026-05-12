#!/usr/bin/env python3
"""
Earnings22 prepare: download Rev's MP3 + ``.nlp`` files, normalize audio to FLAC, build benchmark
references from ``.nlp`` rows.

Outputs:
  data/prepared/earnings22/audio/raw/<file_id>.flac
  data/prepared/benchmark/references/<file_id>.ref.txt
  data/prepared/benchmark/hypotheses/<file_id>.hyp.txt   (placeholder if missing)

Source MP3s and ``.nlp`` files live in ``data/prepared/earnings22/cache/`` for the lifetime of
the prepare run and are wiped on success.

Defaults pick two short calls from ``earnings22/metadata.csv`` (overridable via positional args
or env ``EARNINGS22_FILE_IDS=<id1>,<id2>``).
"""
from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path

from datasets.prepare import (
    cache_dir,
    download_file,
    normalize_to_flac,
    raw_audio_dir,
    raw_audio_path,
    require_ffmpeg,
    write_benchmark_cases,
)

from .transcripts import build_cases

DEFAULT_FILE_IDS = ("4462231", "4469528")
DATASET = "earnings22"

DEFAULT_RAW_BASE = "https://raw.githubusercontent.com/revdotcom/speech-datasets/main"
USER_AGENT = "STT-exploration-earnings22-fetch/1.0"


def _media_url(raw_base: str, file_id: str) -> str:
    """Rev's MP3s are Git LFS objects. ``raw.githubusercontent.com`` returns a tiny pointer file
    that breaks ``ffmpeg``; ``github.com/<u>/<r>/raw/<ref>/…`` redirects to the real bytes."""
    base = raw_base.rstrip("/")
    marker = "raw.githubusercontent.com/"
    if marker in base:
        tail = base.split(marker, 1)[1].strip("/").split("/")
        if len(tail) >= 3:
            user, repo, ref = tail[0], tail[1], tail[2]
            return f"https://github.com/{user}/{repo}/raw/{ref}/earnings22/media/{file_id}.mp3"
    return f"{base}/earnings22/media/{file_id}.mp3"


def _nlp_url(raw_base: str, file_id: str, *, aligned: bool) -> str:
    sub = "force_aligned_nlp_references" if aligned else "nlp_references"
    ext = "aligned.nlp" if aligned else "nlp"
    return f"{raw_base.rstrip('/')}/earnings22/transcripts/{sub}/{file_id}.{ext}"


def _ensure_flac(file_id: str, *, force: bool, raw_base: str, cache: Path) -> Path:
    """Download MP3 into ``cache``, encode to ``audio/raw/<file_id>.flac``."""
    flac = raw_audio_path(DATASET, file_id)
    if flac.is_file() and not force:
        print(f"skip (exists): {flac}", flush=True)
        return flac
    flac.parent.mkdir(parents=True, exist_ok=True)

    src = cache / f"{file_id}.mp3"
    download_file(_media_url(raw_base, file_id), src, force=force, user_agent=USER_AGENT)

    print(f"  encode: {src.name} -> {flac.name}", flush=True)
    normalize_to_flac(src, flac)
    return flac


def _ensure_nlp(file_id: str, *, force: bool, raw_base: str, cache: Path, aligned: bool) -> Path:
    name = f"{file_id}.aligned.nlp" if aligned else f"{file_id}.nlp"
    dst = cache / name
    download_file(
        _nlp_url(raw_base, file_id, aligned=aligned),
        dst,
        force=force,
        user_agent=USER_AGENT,
    )
    return dst


def _file_ids_from_argv_or_env(argv_ids: list[str]) -> list[str]:
    if argv_ids:
        return argv_ids
    env = os.environ.get("EARNINGS22_FILE_IDS", "").strip()
    if env:
        return [x.strip() for x in env.split(",") if x.strip()]
    return list(DEFAULT_FILE_IDS)


def prepare(
    file_ids: list[str],
    *,
    force: bool = False,
    raw_base: str | None = None,
    aligned_nlp: bool = False,
) -> int:
    require_ffmpeg()
    cache = cache_dir(DATASET).resolve()
    cache.mkdir(parents=True, exist_ok=True)
    raw_audio_dir(DATASET).mkdir(parents=True, exist_ok=True)
    base = raw_base or os.environ.get("EARNINGS22_RAW_BASE", DEFAULT_RAW_BASE)

    print(f"[earnings22] audio + transcripts ({len(file_ids)} files) -> {raw_audio_dir(DATASET)}", flush=True)
    nlp_paths: dict[str, Path] = {}
    for fid in file_ids:
        _ensure_flac(fid, force=force, raw_base=base, cache=cache)
        nlp_paths[fid] = _ensure_nlp(fid, force=force, raw_base=base, cache=cache, aligned=aligned_nlp)

    print("[earnings22] reference transcripts …", flush=True)
    write_benchmark_cases(build_cases(nlp_paths))

    shutil.rmtree(cache, ignore_errors=True)
    print(f"[earnings22] done. flac: {raw_audio_dir(DATASET)} ; refs: see data/prepared/benchmark/")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "file_ids",
        nargs="*",
        metavar="FILE_ID",
        help=(
            f"metadata.csv File IDs (default: {' '.join(DEFAULT_FILE_IDS)} "
            f"or env EARNINGS22_FILE_IDS)"
        ),
    )
    p.add_argument(
        "--force-fetch",
        action="store_true",
        help="Re-download and re-encode even if outputs exist",
    )
    p.add_argument(
        "--raw-base",
        default=None,
        help=f"Override Rev raw GitHub base (default env EARNINGS22_RAW_BASE or {DEFAULT_RAW_BASE})",
    )
    p.add_argument(
        "--aligned-nlp",
        action="store_true",
        help="Use force_aligned_nlp_references/<id>.aligned.nlp instead of nlp_references",
    )
    args = p.parse_args(list(argv) if argv is not None else None)
    ids = _file_ids_from_argv_or_env(list(args.file_ids))
    if not ids:
        p.error("no file IDs: pass FILE_ID … or set EARNINGS22_FILE_IDS")
    return prepare(
        ids,
        force=args.force_fetch,
        raw_base=args.raw_base,
        aligned_nlp=args.aligned_nlp,
    )


if __name__ == "__main__":
    raise SystemExit(main())
