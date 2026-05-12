"""
Shared parser for NITE NXT word-XML annotations (used by AMI and ICSI).

Both corpora ship per-channel word files named ``<meeting>.<ch>.words.xml``. AMI marks
punctuation tokens with ``punc="true"``; ICSI marks them via a ``c="…"`` attribute that's not in
the word-like classes. Everything else (parsing tokens, sorting by time then channel, merging
into one transcript) is identical, and lives here.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass, field
from html import unescape
from pathlib import Path

from datasets.prepare.cases import collapse_comma_runs

PuncPredicate = Callable[[ET.Element], bool]


@dataclass
class Word:
    start: float
    end: float
    channel: str
    text: str
    is_punc: bool = False
    nite_id: str = field(default="")

    @property
    def sort_key(self) -> tuple[float, int, str]:
        rank = "ABCDEFG".find(self.channel)
        if rank < 0:
            rank = 99
        return (self.start, rank, self.nite_id or "")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def parse_words(path: Path, *, is_punc: PuncPredicate) -> list[Word]:
    """Parse one ``<meeting>.<ch>.words.xml`` file. Returns one ``Word`` per token."""
    stem = path.stem
    parts = stem.split(".")
    if len(parts) < 3 or parts[-1] != "words":
        return []
    ch = parts[-2]
    if len(ch) != 1 or not ch.isalpha():
        return []

    out: list[Word] = []
    for el in ET.parse(path).getroot().iter():
        if _local_name(el.tag) != "w":
            continue
        st = el.get("starttime")
        et = el.get("endtime", st or "0")
        nite_id = el.get("nite:id") or el.get("{http://nite.sourceforge.net/}id", "") or ""
        punc = is_punc(el)
        raw = el.text or ""
        if not raw.strip() and not punc:
            continue
        try:
            start = float(st) if st is not None else 0.0
            end = float(et) if et is not None else start
        except ValueError:
            continue
        out.append(
            Word(
                start=start,
                end=end,
                channel=ch.upper(),
                text=unescape(raw),
                is_punc=punc,
                nite_id=nite_id,
            )
        )
    return out


def find_word_files(manual_dir: Path, meeting: str) -> list[Path]:
    wd = manual_dir / "words"
    if not wd.is_dir():
        return []
    return sorted(f for f in wd.glob(f"{meeting}.*.words.xml") if f.is_file())


def merge_single_stream(words: list[Word]) -> str:
    """Merge time-ordered words into one transcript line (no speaker labels)."""
    line = ""
    for w in words:
        if w.is_punc:
            line += w.text
        elif line:
            line = line + " " + w.text
        else:
            line = w.text
    return collapse_comma_runs(line.strip())


def merge_speaker_blocks(words: list[Word]) -> str:
    """Merge into per-speaker blocks ``A: …`` separated by blank lines."""
    out_lines: list[str] = []
    cur: str | None = None
    line = ""
    for w in words:
        if w.channel != cur:
            if cur is not None and line.strip():
                out_lines.append(f"{cur}: {collapse_comma_runs(line.strip())}")
            cur = w.channel
            line = ""
        if w.is_punc:
            line += w.text
        elif line:
            line = line + " " + w.text
        else:
            line = w.text
    if cur is not None and line.strip():
        out_lines.append(f"{cur}: {collapse_comma_runs(line.strip())}")
    return "\n\n".join(out_lines) + "\n" if out_lines else ""


def merge_to_transcript(words: list[Word], *, per_channel_blocks: bool = False) -> str:
    if not words:
        return ""
    words = sorted(words, key=lambda w: w.sort_key)
    if per_channel_blocks:
        return merge_speaker_blocks(words)
    body = merge_single_stream(words)
    return body + "\n" if body else ""


def reference_text_for_meeting(
    manual_dir: Path,
    meeting: str,
    *,
    is_punc: PuncPredicate,
) -> str | None:
    """All words for ``meeting``, merged into one transcript line. ``None`` if no XML found."""
    files = find_word_files(manual_dir, meeting)
    if not files:
        return None
    words: list[Word] = []
    for f in files:
        words.extend(parse_words(f, is_punc=is_punc))
    return merge_to_transcript(words)
