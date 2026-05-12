"""
Transcribe chunked audio parts via an OpenAI-compatible audio API and write benchmark hypotheses.

Pipeline (one call per case_id):

    audio/chunked/<case_id>/part0001.{flac|wav}, …  (from :mod:`lib.chunking`)
        -> POST each to ``audio.transcriptions``                       (:class:`TranscriptionClient`)
        -> merge per-part texts (:func:`shared.lib.merge_transcripts.merge_overlapping_texts`)
        -> data/prepared/benchmark/hypotheses/<case_id>.hyp.txt

Use ``--chunk-format wav`` (or ``mp3``) or env ``BENCHMARK_CHUNK_FORMAT`` if the API rejects FLAC or WAV uploads are too large (try ``mp3`` for smaller requests).

For resume after partial runs, :func:`transcribe_case` accepts ``skip_existing`` (CLI ``--resume-transcribe``), using :func:`datasets.prepare.cases.hypothesis_is_placeholder` on existing ``*.hyp.txt`` files.

Auth: ``AQUAVOICE_API_KEY`` (preferred) or ``OPENAI_API_KEY``; optional ``AQUAVOICE_BASE_URL``.
Default model is ``avalon-v1.5``; override with ``model=`` or env ``AQUAVOICE_MODEL``.

Transient ``503`` / connection limits: uploads are retried with exponential backoff
(``BENCHMARK_TRANSCRIBE_MAX_RETRIES``, ``BENCHMARK_TRANSCRIBE_RETRY_BASE_S``, ``BENCHMARK_TRANSCRIBE_RETRY_CAP_S``).
"""
from __future__ import annotations

import os
import random
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from datasets.prepare import benchmark_hypotheses_dir, chunked_audio_dir
from datasets.prepare.cases import hypothesis_is_placeholder
from lib.chunking import chunk_glob
from shared.lib.merge_transcripts import merge_overlapping_texts

DEFAULT_BASE_URL = "https://api.aquavoice.com/api/v1"
DEFAULT_MODEL = "avalon-v1.5"

_MIME_BY_SUFFIX = {
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
}


def _transcribe_retry_params() -> tuple[int, float, float]:
    """(max_attempts, base_sleep_s, cap_sleep_s)."""
    try:
        n = max(1, int(os.environ.get("BENCHMARK_TRANSCRIBE_MAX_RETRIES", "8").strip()))
    except ValueError:
        n = 8
    try:
        base = float(os.environ.get("BENCHMARK_TRANSCRIBE_RETRY_BASE_S", "4").strip())
    except ValueError:
        base = 4.0
    try:
        cap = float(os.environ.get("BENCHMARK_TRANSCRIBE_RETRY_CAP_S", "120").strip())
    except ValueError:
        cap = 120.0
    base = max(0.25, base)
    cap = max(base, cap)
    return (n, base, cap)


def _import_openai() -> Any:
    try:
        from openai import OpenAI
    except ImportError as e:
        raise SystemExit("Install the OpenAI SDK: ``uv sync --project .``") from e
    return OpenAI


class TranscriptionClient:
    """Thin wrapper around ``openai.audio.transcriptions`` for one-file uploads."""

    def __init__(self, client: Any) -> None:
        self._client = client

    @classmethod
    def from_env(cls, *, base_url: str | None = None, api_key: str | None = None) -> TranscriptionClient:
        OpenAI = _import_openai()
        key = api_key or os.environ.get("AQUAVOICE_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise SystemExit(
                "Set AQUAVOICE_API_KEY (recommended) or OPENAI_API_KEY in the environment."
            )
        url = (base_url or os.environ.get("AQUAVOICE_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
        return cls(OpenAI(api_key=key, base_url=url))

    def transcribe_file(self, audio_path: Path, *, model: str) -> str:
        """Upload one file to ``audio.transcriptions``; returns the text body.

        Retries on transient provider errors (5xx-style ``InternalServerError``, ``429``,
        ``APIConnectionError`` / ``APITimeoutError``).
        """
        from openai import APIConnectionError, InternalServerError, RateLimitError

        mime = _MIME_BY_SUFFIX.get(audio_path.suffix.lower(), "audio/flac")
        max_attempts, base_s, cap_s = _transcribe_retry_params()
        transient = (InternalServerError, RateLimitError, APIConnectionError)

        delay = base_s
        for attempt in range(1, max_attempts + 1):
            try:
                with audio_path.open("rb") as f:
                    result = self._client.audio.transcriptions.create(
                        model=model,
                        file=(audio_path.name, f, mime),
                    )
                if isinstance(result, str):
                    return result.strip()
                text = getattr(result, "text", None)
                return (str(text) if text is not None else str(result)).strip()
            except transient as e:  # type: ignore[misc]
                if attempt >= max_attempts:
                    raise
                sleep_s = min(cap_s, delay)
                jitter = sleep_s * random.uniform(-0.1, 0.2)
                wait = max(base_s * 0.25, sleep_s + jitter)
                print(
                    f"[transcribe] {audio_path.name}: transient {type(e).__name__}; "
                    f"retry {attempt + 1}/{max_attempts} after {wait:.1f}s",
                    flush=True,
                )
                time.sleep(wait)
                delay = min(cap_s, delay * 2)

        raise AssertionError("transcribe_file: unreachable")


def _list_chunks(dataset: str, case_id: str, *, chunk_format: str = "flac") -> list[Path]:
    parts = sorted((chunked_audio_dir(dataset) / case_id).glob(chunk_glob(chunk_format)))
    if not parts:
        raise FileNotFoundError(
            f"no chunks for {dataset}/{case_id} under {chunked_audio_dir(dataset) / case_id} "
            f"(run chunking first; expected {chunk_glob(chunk_format)})"
        )
    return parts


def transcribe_case(
    client: TranscriptionClient,
    dataset: str,
    case_id: str,
    *,
    model: str,
    chunk_format: str = "flac",
    out_hyp_dir: Path | None = None,
    log: bool = True,
    skip_existing: bool = False,
) -> Path:
    """
    Transcribe every part of one chunked case and write
    ``data/prepared/benchmark/hypotheses/<case_id>.hyp.txt``. Returns the path written.

    With ``skip_existing=True``, skips API calls when the hypothesis file exists and is not the
    prepare placeholder (resume after a crash without redoing finished meetings).
    """
    out_dir = (out_hyp_dir or benchmark_hypotheses_dir()).resolve()
    hyp_path = out_dir / f"{case_id}.hyp.txt"
    if skip_existing and hyp_path.is_file():
        prev = hyp_path.read_text(encoding="utf-8")
        if not hypothesis_is_placeholder(prev):
            if log:
                print(
                    f"[transcribe] {dataset}/{case_id}: skip (reuse {hyp_path.name})",
                    flush=True,
                )
            return hyp_path

    parts = _list_chunks(dataset, case_id, chunk_format=chunk_format)
    n = len(parts)
    texts: list[str] = []
    for i, part in enumerate(parts, 1):
        if log:
            size_kib = part.stat().st_size // 1024
            print(
                f"[transcribe] {dataset}/{case_id}: part {i}/{n} ({size_kib} KiB) -> API …",
                flush=True,
            )
        t0 = time.perf_counter()
        texts.append(client.transcribe_file(part, model=model))
        if log:
            print(
                f"[transcribe] {dataset}/{case_id}: part {i}/{n} done in {time.perf_counter() - t0:.1f}s",
                flush=True,
            )

    text = merge_overlapping_texts(texts)
    out_dir.mkdir(parents=True, exist_ok=True)
    hyp_path.write_text(text + "\n", encoding="utf-8")
    if log:
        print(
            f"[transcribe] {dataset}/{case_id}: merged {n} parts -> {hyp_path} ({len(text)} chars)",
            flush=True,
        )
    return hyp_path


def transcribe_dataset(
    dataset: str,
    case_ids: Sequence[str],
    *,
    model: str = DEFAULT_MODEL,
    chunk_format: str = "flac",
    client: TranscriptionClient | None = None,
    out_hyp_dir: Path | None = None,
    log: bool = True,
    skip_existing: bool = False,
) -> int:
    """
    Transcribe every chunked case in ``case_ids`` and write hypothesis files. Returns ``0`` on
    success or ``1`` if a case has no chunks.

    ``skip_existing`` is forwarded to :func:`transcribe_case` ``).
    """
    cli = client or TranscriptionClient.from_env()
    for case_id in case_ids:
        try:
            transcribe_case(
                cli,
                dataset,
                case_id,
                model=model,
                chunk_format=chunk_format,
                out_hyp_dir=out_hyp_dir,
                log=log,
                skip_existing=skip_existing,
            )
        except FileNotFoundError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
    return 0
