"""AMI reference transcripts: build one ``BenchmarkCase`` per meeting from manual word XML."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Sequence
from pathlib import Path

from datasets.prepare import BenchmarkCase, reference_text_for_meeting


def _is_punc(el: ET.Element) -> bool:
    """AMI marks punctuation tokens with ``punc="true"``."""
    return str(el.get("punc", "")).lower() in ("1", "true", "yes")


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
