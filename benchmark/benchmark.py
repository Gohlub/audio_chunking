#!/usr/bin/env -S uv run --project .
"""
End-to-end STT benchmark over one or more prepared datasets.

Pipeline (each stage is its own module; this script just orchestrates them):

    1. ``datasets.<name>.prepare``   download + normalize -> data/prepared/<name>/audio/raw/
    2. :mod:`lib.chunking`       raw FLAC          -> data/prepared/<name>/audio/chunked/
    3. :mod:`lib.transcription`  chunks            -> data/prepared/benchmark/hypotheses/
    4. :mod:`evaluation.tests`       refs vs hyps      -> WER + semantic report

Defaults run all three registered datasets (``ami``, ``icsi``, ``earnings22``) with their
prepare-script default case ids. Pass dataset ids positionally to restrict the run::

    uv run --project . benchmark.py
    uv run --project . benchmark.py ami
    uv run --project . benchmark.py ami icsi --skip-prepare
    uv run --project . benchmark.py --chunk-seconds 300 --overlap-seconds 10
    uv run --project . benchmark.py --chunk-seconds 600 --overlap-seconds 10  # longer chunks

Use ``--resume-transcribe`` with ``--skip-prepare`` / ``--skip-chunk`` to skip cases that already
have a non-placeholder ``*.hyp.txt``. Transient API errors use retries (env
``BENCHMARK_TRANSCRIBE_*``; see :mod:`lib.transcription` / ``benchmark/README.md``).

Auth (only required when actually transcribing): ``AQUAVOICE_API_KEY`` or ``OPENAI_API_KEY``.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib import chunking, transcription  # noqa: E402
from datasets import default_case_ids, list_dataset_ids, run_prepare as prepare_dataset  # noqa: E402
from evaluation.tests import run_all_tests  # noqa: E402

DEFAULT_CHUNK_SECONDS = 300.0
DEFAULT_OVERLAP_SECONDS = 10.0

_ENV_CHUNK_FMT = os.environ.get("BENCHMARK_CHUNK_FORMAT", "flac").strip().lower()
CHUNK_FORMAT_DEFAULT = _ENV_CHUNK_FMT if _ENV_CHUNK_FMT in ("flac", "wav", "mp3") else "flac"


def _stage(label: str) -> float:
    print(f"\n>>> {label} …", flush=True)
    return time.perf_counter()


def _done(label: str, t0: float) -> None:
    print(f">>> {label} finished in {time.perf_counter() - t0:.1f}s", flush=True)


def _selected_datasets(argv_datasets: list[str]) -> list[str]:
    if not argv_datasets:
        return list_dataset_ids()
    known = set(list_dataset_ids())
    bad = [d for d in argv_datasets if d not in known]
    if bad:
        raise SystemExit(
            f"unknown dataset(s): {', '.join(bad)}; known: {', '.join(sorted(known))}"
        )
    return argv_datasets


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "datasets",
        nargs="*",
        help=f"Dataset ids to run (default: {' '.join(list_dataset_ids())}).",
    )
    p.add_argument("--skip-prepare", action="store_true", help="Skip download/normalize step (assumes audio/raw/<id>.flac exists).")
    p.add_argument("--skip-chunk", action="store_true", help="Skip chunking (assumes audio/chunked/<id>/ already has parts for the chosen format).")
    p.add_argument("--skip-transcribe", action="store_true", help="Skip API transcription (keep existing benchmark hypotheses).")
    p.add_argument("--skip-tests", action="store_true", help="Skip the WER + semantic report at the end.")
    p.add_argument(
        "--resume-transcribe",
        action="store_true",
        help="Skip transcription for meetings that already have a non-placeholder hypotheses file.",
    )
    p.add_argument(
        "--chunk-seconds",
        type=float,
        default=float(os.environ.get("STT_CHUNK_SECONDS", DEFAULT_CHUNK_SECONDS)),
        help=f"Chunk length in seconds (default: env STT_CHUNK_SECONDS or {DEFAULT_CHUNK_SECONDS}).",
    )
    p.add_argument(
        "--overlap-seconds",
        type=float,
        default=float(os.environ.get("STT_OVERLAP_SECONDS", DEFAULT_OVERLAP_SECONDS)),
        help=f"Overlap between adjacent chunks in seconds (default: env STT_OVERLAP_SECONDS or {DEFAULT_OVERLAP_SECONDS}).",
    )
    p.add_argument(
        "--model",
        default=os.environ.get("AQUAVOICE_MODEL", transcription.DEFAULT_MODEL),
        help=f"Transcription model id (default: env AQUAVOICE_MODEL or {transcription.DEFAULT_MODEL}).",
    )
    p.add_argument(
        "--chunk-format",
        choices=["flac", "wav", "mp3"],
        default=CHUNK_FORMAT_DEFAULT,
        help=(
            "On-disk chunk codec/extension (default: env BENCHMARK_CHUNK_FORMAT or flac). "
            "wav: PCM for picky APIs; mp3: smaller uploads (env BENCHMARK_CHUNK_MP3_BITRATE, default 128k)."
        ),
    )
    p.add_argument("--force-fetch", action="store_true", help="Pass --force-fetch to each prepare script (re-download + re-encode).")
    p.add_argument("--force-chunk", action="store_true", help="Re-chunk even if audio/chunked/<id>/ already has parts.")
    args = p.parse_args(list(argv) if argv is not None else None)

    selected = _selected_datasets(list(args.datasets))
    cases_by_dataset: dict[str, list[str]] = {ds: default_case_ids(ds) for ds in selected}

    if not args.skip_transcribe:
        if not (os.environ.get("AQUAVOICE_API_KEY") or os.environ.get("OPENAI_API_KEY")):
            print("error: set AQUAVOICE_API_KEY or OPENAI_API_KEY to transcribe.", file=sys.stderr)
            return 1

    if not args.skip_prepare:
        for ds in selected:
            t0 = _stage(f"[prepare] {ds}")
            argv_ds: list[str] = []
            if args.force_fetch:
                argv_ds.append("--force-fetch")
            rc = prepare_dataset(ds, argv_ds)
            if rc != 0:
                return rc
            _done(f"[prepare] {ds}", t0)

    if not args.skip_chunk:
        for ds in selected:
            t0 = _stage(
                f"[chunk] {ds} (chunk={args.chunk_seconds}s, overlap={args.overlap_seconds}s, "
                f"format={args.chunk_format})"
            )
            chunking.chunk_dataset(
                ds,
                cases_by_dataset[ds],
                chunk_seconds=args.chunk_seconds,
                overlap_seconds=args.overlap_seconds,
                chunk_format=args.chunk_format,
                force=args.force_chunk,
            )
            _done(f"[chunk] {ds}", t0)

    if not args.skip_transcribe:
        client = transcription.TranscriptionClient.from_env()
        for ds in selected:
            t0 = _stage(f"[transcribe] {ds} (model={args.model}, chunk_format={args.chunk_format})")
            rc = transcription.transcribe_dataset(
                ds,
                cases_by_dataset[ds],
                model=args.model,
                chunk_format=args.chunk_format,
                client=client,
                skip_existing=args.resume_transcribe,
            )
            if rc != 0:
                return rc
            _done(f"[transcribe] {ds}", t0)

    if not args.skip_tests:
        t0 = _stage("[metrics] WER + semantic")
        run_all_tests()
        _done("[metrics]", t0)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
