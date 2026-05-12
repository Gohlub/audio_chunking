"""
Benchmark case contract.

A ``BenchmarkCase`` is one stable ``case_id`` plus its reference transcript text. Dataset
``prepare`` modules build a list of cases and call :func:`write_benchmark_cases`, which writes
``<case_id>.ref.txt`` to ``data/prepared/benchmark/references/`` and ensures a placeholder
``<case_id>.hyp.txt`` exists in ``data/prepared/benchmark/hypotheses/`` so ``evaluation/`` can pair
them. STT runs later overwrite the hypothesis file. :func:`hypothesis_is_placeholder` detects that
stub for resume/skip logic in :mod:`lib.transcription`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from datasets.prepare.paths import benchmark_hypotheses_dir, benchmark_references_dir

_HYP_PLACEHOLDER = "[placeholder: replace with your STT transcript]\n"
_COMMA_RUN_RE = re.compile(r",{2,}")


def hypothesis_is_placeholder(text: str) -> bool:
    """Whether ``text`` is the benchmark prepare stub (STT never wrote this meeting yet)."""
    s = text.strip()
    return s == _HYP_PLACEHOLDER.strip() or s.startswith("[placeholder:")


def collapse_comma_runs(text: str) -> str:
    """Collapse runs of NXT comma tokens (``,,``, ``,,,``…) into a single ``,``."""
    return _COMMA_RUN_RE.sub(",", text)


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    reference_text: str
    hypothesis_text: str = _HYP_PLACEHOLDER


def write_benchmark_cases(
    cases: list[BenchmarkCase],
    *,
    out_ref: Path | None = None,
    out_hyp: Path | None = None,
    keep_existing_hypotheses: bool = True,
) -> None:
    """
    Write ``<case_id>.ref.txt`` (always) and ``<case_id>.hyp.txt`` (placeholder, only if missing
    or ``keep_existing_hypotheses=False``) for each case.
    """
    ref_dir = (out_ref or benchmark_references_dir()).resolve()
    hyp_dir = (out_hyp or benchmark_hypotheses_dir()).resolve()
    ref_dir.mkdir(parents=True, exist_ok=True)
    hyp_dir.mkdir(parents=True, exist_ok=True)

    for case in cases:
        ref_path = ref_dir / f"{case.case_id}.ref.txt"
        hyp_path = hyp_dir / f"{case.case_id}.hyp.txt"
        ref_path.write_text(case.reference_text, encoding="utf-8")
        if not (keep_existing_hypotheses and hyp_path.exists()):
            hyp_path.write_text(case.hypothesis_text, encoding="utf-8")
        print(
            f"benchmark: wrote {ref_path} ({len(case.reference_text)} chars) and {hyp_path}",
            flush=True,
        )
