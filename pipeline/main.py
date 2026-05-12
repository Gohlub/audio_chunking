"""Audio-to-text pipeline scaffold using CocoIndex + Postgres.

Initial setup mirrors CocoIndex's audio_to_text example, but source inputs are
driven by environment variables so replacing data sources later is trivial.
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import tempfile
from dataclasses import dataclass
from typing import AsyncIterator

import asyncpg
import cocoindex as coco
from cocoindex.connectors import localfs, postgres
from cocoindex.ops.litellm import LiteLLMTranscriber
from cocoindex.resources.file import PatternFilePathMatcher

from lib.async_chunking import ChunkingConfig, chunk_audio
from lib.merge_transcripts import merge_overlapping_texts


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


DATABASE_URL = os.getenv(
    "POSTGRES_URL",
    "postgres://cocoindex:cocoindex@localhost/cocoindex",
)
TABLE_NAME = os.getenv("PIPELINE_TABLE_NAME", "audio_transcriptions")
PG_SCHEMA_NAME = os.getenv("PIPELINE_PG_SCHEMA", "pipeline")
SOURCE_DIR = pathlib.Path(os.getenv("PIPELINE_SOURCE_DIR", "./audio_files"))
MODEL_NAME = os.getenv("PIPELINE_TRANSCRIBER_MODEL", "whisper-1")
VAD_SR = int(os.getenv("PIPELINE_VAD_SAMPLE_RATE", "16000"))
VAD_THRESHOLD = float(os.getenv("PIPELINE_VAD_THRESHOLD", "0.5"))
CHUNKING_STRATEGY = os.getenv("PIPELINE_CHUNKING_STRATEGY", "hybrid")
CHUNK_SECONDS = float(os.getenv("PIPELINE_CHUNK_SECONDS", "600"))
CHUNK_OVERLAP_SECONDS = float(os.getenv("PIPELINE_CHUNK_OVERLAP_SECONDS", "5"))
CHUNK_MAX_DIRECT_BYTES = int(os.getenv("PIPELINE_CHUNK_MAX_DIRECT_BYTES", "25000000"))
CHUNK_MAX_DIRECT_SECONDS = float(os.getenv("PIPELINE_CHUNK_MAX_DIRECT_SECONDS", "1080"))
CHUNK_HYBRID_SILENCE_MIN_DURATION = float(
    os.getenv("PIPELINE_CHUNK_HYBRID_SILENCE_MIN_DURATION", "10")
)
CHUNK_SILENCE_THRESHOLD_DB = float(
    os.getenv("PIPELINE_CHUNK_SILENCE_THRESHOLD_DB", "-35")
)
CHUNK_SILENCE_MIN_DURATION = float(
    os.getenv("PIPELINE_CHUNK_SILENCE_MIN_DURATION", "0.5")
)
CHUNK_MIN_SECONDS = float(os.getenv("PIPELINE_CHUNK_MIN_SECONDS", "0.2"))
CHUNK_NORMALIZE_AUDIO = _env_bool("PIPELINE_CHUNK_NORMALIZE_AUDIO", True)

# Comma-separated override is easy for later source changes.
# Example: PIPELINE_AUDIO_PATTERNS=**/*.wav,**/*.mp3
_patterns_env = os.getenv("PIPELINE_AUDIO_PATTERNS")
AUDIO_PATTERNS = (
    [p.strip() for p in _patterns_env.split(",") if p.strip()]
    if _patterns_env
    else [
        "**/*.aac",
        "**/*.aiff",
        "**/*.flac",
        "**/*.m4a",
        "**/*.mp3",
        "**/*.ogg",
        "**/*.wav",
        "**/*.webm",
    ]
)

PG_DB = coco.ContextKey[asyncpg.Pool]("audio_to_text_db")


_chunking_config = ChunkingConfig(
    strategy=CHUNKING_STRATEGY,
    chunk_seconds=CHUNK_SECONDS,
    overlap_seconds=CHUNK_OVERLAP_SECONDS,
    max_direct_bytes=CHUNK_MAX_DIRECT_BYTES,
    max_direct_seconds=CHUNK_MAX_DIRECT_SECONDS,
    hybrid_silence_min_duration=CHUNK_HYBRID_SILENCE_MIN_DURATION,
    hybrid_vad_threshold=VAD_THRESHOLD,
    hybrid_vad_sample_rate=VAD_SR,
    silence_threshold_db=CHUNK_SILENCE_THRESHOLD_DB,
    silence_min_duration=CHUNK_SILENCE_MIN_DURATION,
    min_chunk_seconds=CHUNK_MIN_SECONDS,
    normalize_audio=CHUNK_NORMALIZE_AUDIO,
)


@dataclass(frozen=True)
class PipelineProcessingConfig:
    model_name: str
    chunking: ChunkingConfig


_processing_config = PipelineProcessingConfig(
    model_name=MODEL_NAME,
    chunking=_chunking_config,
)
_transcriber = LiteLLMTranscriber(_processing_config.model_name)


@dataclass
class AudioTranscription:
    filename: str
    text: str


@dataclass
class _PathFileLike:
    file_path: pathlib.Path

    async def read(self) -> bytes:
        return await asyncio.to_thread(self.file_path.read_bytes)


@coco.lifespan
async def coco_lifespan(builder: coco.EnvironmentBuilder) -> AsyncIterator[None]:
    async with await asyncpg.create_pool(DATABASE_URL) as pool:
        builder.provide(PG_DB, pool)
        yield


@coco.fn(memo=True, deps=_processing_config)
async def process_file(
    file: localfs.File,
    table: postgres.TableTarget[AudioTranscription],
) -> None:
    audio_path = pathlib.Path(str(file.file_path.path))
    transcript = ""
    with tempfile.TemporaryDirectory(prefix="chunking-") as tmpdir:
        chunk_paths = await chunk_audio(
            audio_path,
            pathlib.Path(tmpdir),
            _processing_config.chunking,
        )
        chunk_texts: list[str] = []
        for chunk_path in chunk_paths:
            chunk_text = (await _transcriber.transcribe(_PathFileLike(chunk_path))).strip()
            if chunk_text:
                chunk_texts.append(chunk_text)
        transcript = merge_overlapping_texts(chunk_texts)
    table.declare_row(
        row=AudioTranscription(
            filename=str(file.file_path.path),
            text=transcript,
        ),
    )


@coco.fn
async def app_main(sourcedir: pathlib.Path) -> None:
    target_table = await postgres.mount_table_target(
        PG_DB,
        table_name=TABLE_NAME,
        table_schema=await postgres.TableSchema.from_class(
            AudioTranscription,
            primary_key=["filename"],
        ),
        pg_schema_name=PG_SCHEMA_NAME,
    )

    files = localfs.walk_dir(
        sourcedir,
        recursive=True,
        path_matcher=PatternFilePathMatcher(included_patterns=AUDIO_PATTERNS),
    )
    await coco.mount_each(process_file, files.items(), target_table)


app = coco.App(
    "AudioToText",
    app_main,
    sourcedir=SOURCE_DIR,
)
