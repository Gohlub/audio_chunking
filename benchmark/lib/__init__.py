"""
Post-prepare benchmark stages (dataset-agnostic).

After ``datasets.<name>.prepare`` has written raw FLAC and reference transcripts under
``data/prepared/``, this package covers everything until scoring:

  :mod:`lib.chunking` — slice raw FLAC into overlapping parts under ``audio/chunked/``
  :mod:`lib.transcription` — call the STT API and merge overlaps into ``benchmark/hypotheses/``

Overlap merge and related helpers live in :mod:`shared.lib` (installable ``../shared`` tree).

Import submodules (``from lib.chunking import chunk_dataset``) or names from them.
"""
from __future__ import annotations

from . import chunking, transcription

__all__ = ["chunking", "transcription"]
