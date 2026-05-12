"""ICSI reference transcripts: build one ``BenchmarkCase`` per meeting from manual word XML."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Sequence
from pathlib import Path

from datasets.prepare import BenchmarkCase, reference_text_for_meeting

# ICSI ``words.xml`` uses ``c="W"`` (words), ``c="CM"`` / ``c="."`` / quotes / hyphens / etc.
# for punctuation. It does *not* use the AMI-style ``punc="true"`` attribute on word-like tokens,
# so we classify by the ``c`` attribute instead.
_WORD_LIKE_C = frozenset({"W", "TRUNCW", "LET", "ABBR"})


def _is_punc(el: ET.Element) -> bool:
    if str(el.get("punc", "")).lower() in ("1", "true", "yes"):
        return True
    c = el.get("c")
    return bool(c) and c not in _WORD_LIKE_C


def reference_text(manual_dir: Path, meeting: str) -> str | None:
    return reference_text_for_meeting(manual_dir, meeting, is_punc=_is_punc)


def build_cases(manual_dir: Path, meetings: Sequence[str]) -> list[BenchmarkCase]:
    cases: list[BenchmarkCase] = []
    for m in meetings:
        text = reference_text(manual_dir, m)
        if text is None:
            print(f"skip {m}: no words/*.words.xml under {manual_dir / 'words'}")
            continue
        cases.append(BenchmarkCase(case_id=m, reference_text=text))
    return cases
