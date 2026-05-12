"""
Earnings22 reference transcripts.

Rev's ``.nlp`` files are ``|``-delimited rows: ``token|speaker|ts|endTs|punctuation|case|tags|wer_tags``.
We rebuild the surface transcript by concatenating ``token + punctuation`` per row, separated by
single spaces. WER/semantic normalization happens later in ``evaluation/`` — we keep the
publisher-faithful surface string in ``.ref.txt``.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from datasets.prepare import BenchmarkCase


@dataclass(frozen=True)
class NLPRow:
    token: str
    speaker: str
    ts: str
    end_ts: str
    punctuation: str
    case: str
    tags: str
    wer_tags: str


def _split(line: str) -> list[str]:
    return list(next(csv.reader([line], delimiter="|"), []))


def parse_nlp(path: Path) -> list[NLPRow]:
    out: list[NLPRow] = []
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = _split(line)
        if len(parts) < 2 or parts[0].strip().lower() == "token":
            continue
        while len(parts) < 8:
            parts.append("")
        out.append(NLPRow(*parts[:8]))
    return out


def reference_text(nlp_path: Path) -> str:
    chunks: list[str] = []
    for r in parse_nlp(nlp_path):
        tok = r.token.strip()
        if not tok:
            continue
        chunks.append(tok + r.punctuation.strip())
    body = " ".join(chunks).strip()
    return body + ("\n" if body else "")


def build_cases(file_id_to_nlp: dict[str, Path]) -> list[BenchmarkCase]:
    return [
        BenchmarkCase(case_id=fid, reference_text=reference_text(p))
        for fid, p in file_id_to_nlp.items()
    ]
