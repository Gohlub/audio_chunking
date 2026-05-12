"""
Merge overlapping partial transcripts using longest-common-sequence alignment.

Used by benchmark transcription and by the CocoIndex pipeline after per-chunk STT.
"""
from __future__ import annotations

import re


def merge_overlapping_texts(texts: list[str]) -> str:
    """
    Merge per-part transcripts into one string by trimming overlap with longest-common-sequence
    alignment (``find_longest_common_sequence``). Empty parts are skipped; a single part is
    returned as-is.
    """
    parts = [t.strip() for t in texts if t.strip()]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return find_longest_common_sequence(parts, match_by_words=True)


def find_longest_common_sequence(sequences: list[str], match_by_words: bool = True) -> str:
    """
    Align consecutive sequences by their best overlap and concatenate:

      - tokenize each sequence (whitespace-prefixed words by default)
      - for each adjacent pair, slide one over the other and pick the alignment with the
        most token matches (epsilon-tiebreak prefers longer overlaps)
      - keep the left half of the left sequence and the right half of the right sequence
        at the chosen midpoint, then continue with the right sequence as the new "left".
    """
    if not sequences:
        return ""

    if match_by_words:
        token_sequences: list[list[str]] = [
            [word for word in re.split(r"(\s+\w+)", seq) if word]
            for seq in sequences
        ]
    else:
        token_sequences = [list(seq) for seq in sequences]

    left_sequence = token_sequences[0]
    left_length = len(left_sequence)
    total: list[str] = []

    for right_sequence in token_sequences[1:]:
        max_matching = 0.0
        right_length = len(right_sequence)
        max_indices = (left_length, left_length, 0, 0)

        for i in range(1, left_length + right_length + 1):
            eps = float(i) / 10000.0

            left_start = max(0, left_length - i)
            left_stop = min(left_length, left_length + right_length - i)
            left = left_sequence[left_start:left_stop]

            right_start = max(0, i - left_length)
            right_stop = min(right_length, i)
            right = right_sequence[right_start:right_stop]

            if len(left) != len(right):
                continue

            matches = sum(a == b for a, b in zip(left, right))
            score = matches / float(i) + eps
            if matches > 1 and score > max_matching:
                max_matching = score
                max_indices = (left_start, left_stop, right_start, right_stop)

        left_start, left_stop, right_start, right_stop = max_indices
        left_mid = (left_stop + left_start) // 2
        right_mid = (right_stop + right_start) // 2

        total.extend(left_sequence[:left_mid])
        left_sequence = right_sequence[right_mid:]
        left_length = len(left_sequence)

    total.extend(left_sequence)
    return "".join(total)
