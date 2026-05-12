#!/usr/bin/env -S uv run --project .
"""
WER and semantic-similarity tests over the canonical layout:

    data/prepared/benchmark/references/<case_id>.ref.txt
    data/prepared/benchmark/hypotheses/<case_id>.hyp.txt

Pairs are discovered by stem: every ``<case_id>.ref.txt`` is matched with ``<case_id>.hyp.txt``.
Pass a ``config`` dict to :func:`run_all_tests` or the ``run_*_on_dir`` helpers to override paths
or set ``strip_speaker_labels`` (drops ``A: `` / ``B: `` speaker-prefix lines before scoring;
enabled by default for meeting-style references).

Run as a script for the combined report::

    uv run --project . evaluation/tests.py

Or import :func:`run_all_tests` from another module.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

# Canonical paths relative to ``scripts_root()`` (same layout as ``datasets.prepare.paths``).
_DEFAULT_EVAL: dict[str, object] = {
    "strip_speaker_labels": True,
    "reference_dir": "data/prepared/benchmark/references",
    "hypothesis_dir": "data/prepared/benchmark/hypotheses",
}


def default_eval_config() -> dict[str, object]:
    """Fresh copy of the built-in evaluation settings (paths + preprocessing)."""
    return dict(_DEFAULT_EVAL)


def scripts_root() -> Path:
    """Directory that contains ``evaluation/``, ``data/``, and ``pyproject.toml``."""
    return Path(__file__).resolve().parent.parent


def default_data_dir() -> Path:
    return scripts_root() / "data" / "prepared" / "benchmark"


def _resolve_config_path(path_value: object) -> Path | None:
    if not path_value:
        return None
    p = Path(str(path_value))
    return p if p.is_absolute() else scripts_root() / p


def find_transcript_pairs(reference_dir: Path, hypothesis_dir: Path) -> list[tuple[str, Path, Path]]:
    pairs: list[tuple[str, Path, Path]] = []
    for ref_path in sorted(reference_dir.glob("*.ref.txt")):
        case_name = ref_path.name[: -len(".ref.txt")]
        hyp_path = hypothesis_dir / f"{case_name}.hyp.txt"
        if hyp_path.exists():
            pairs.append((case_name, ref_path, hyp_path))
    return pairs


def _strip_speaker_labels(text: str) -> str:
    return re.sub(r"(?m)^\s*[A-Za-z][\w .'-]{0,50}:\s*", "", text)


def _preprocess(text: str, config: dict) -> str:
    if config.get("strip_speaker_labels"):
        text = _strip_speaker_labels(text)
    return text


def _normalize_words(text: str) -> list[str]:
    """Lowercase, strip punctuation, split into tokens (word-level fidelity only)."""
    text = text.lower()
    text = re.sub(r"[^\w\s']", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.split()


def calculate_wer(reference_text: str, hypothesis_text: str) -> dict:
    ref = _normalize_words(reference_text)
    hyp = _normalize_words(hypothesis_text)
    n, m = len(ref), len(hyp)

    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if ref[i - 1] == hyp[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j - 1], dp[i - 1][j], dp[i][j - 1])

    errors = dp[n][m]
    wer = errors / n if n else 0.0
    return {
        "reference_word_count": n,
        "hypothesis_word_count": m,
        "edit_distance": errors,
        "wer": wer,
        "accuracy": 1 - wer,
    }


def run_wer_on_dir(data_dir: Path | str, *, config: dict | None = None) -> dict:
    data_dir = Path(data_dir)
    config = config or default_eval_config()
    reference_dir = _resolve_config_path(config.get("reference_dir")) or data_dir
    hypothesis_dir = _resolve_config_path(config.get("hypothesis_dir")) or data_dir
    pairs = find_transcript_pairs(reference_dir, hypothesis_dir)
    results: dict = {}
    for case_name, ref_path, hyp_path in pairs:
        ref_text = _preprocess(ref_path.read_text(encoding="utf-8"), config)
        hyp_text = _preprocess(hyp_path.read_text(encoding="utf-8"), config)
        results[case_name] = calculate_wer(ref_text, hyp_text)
    return results


def _clean_text_for_semantic(text: str) -> str:
    """Light cleanup that preserves wording so semantics still compare full meaning."""
    return re.sub(r"\s+", " ", text.lower()).strip()


def _interpret_semantic_score(score: float) -> str:
    if score >= 0.90:
        return "Very similar meaning."
    if score >= 0.80:
        return "Mostly similar meaning."
    if score >= 0.70:
        return "Some semantic loss or drift."
    return "Significant semantic difference."


def calculate_semantic_similarity(reference_text: str, hypothesis_text: str, model=None) -> float:
    """Cosine similarity of MiniLM sentence embeddings (lazy-loaded on first call)."""
    from sentence_transformers import SentenceTransformer
    from sklearn.metrics.pairwise import cosine_similarity

    model = model or SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    embeddings = model.encode([_clean_text_for_semantic(reference_text), _clean_text_for_semantic(hypothesis_text)])
    return float(cosine_similarity([embeddings[0]], [embeddings[1]])[0][0])


def run_semantic_on_dir(data_dir: Path | str, *, config: dict | None = None) -> dict:
    data_dir = Path(data_dir)
    config = config or default_eval_config()
    reference_dir = _resolve_config_path(config.get("reference_dir")) or data_dir
    hypothesis_dir = _resolve_config_path(config.get("hypothesis_dir")) or data_dir
    pairs = find_transcript_pairs(reference_dir, hypothesis_dir)
    results: dict = {}
    if not pairs:
        return results

    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    for case_name, ref_path, hyp_path in pairs:
        ref_text = _preprocess(ref_path.read_text(encoding="utf-8"), config)
        hyp_text = _preprocess(hyp_path.read_text(encoding="utf-8"), config)
        score = calculate_semantic_similarity(ref_text, hyp_text, model=model)
        results[case_name] = {"score": score, "interpretation": _interpret_semantic_score(score)}
    return results


def _print_report(wer_results: dict, semantic_results: dict) -> None:
    case_names = sorted(set(wer_results) | set(semantic_results))
    if not case_names:
        print("No transcript pairs found (check paths under data/prepared/benchmark/).")
        print("Expected: data/prepared/benchmark/references/<case>.ref.txt and")
        print("          data/prepared/benchmark/hypotheses/<case>.hyp.txt")
        return

    print("STT Evaluation Report")
    print("=" * 35)
    for case_name in case_names:
        print(f"[{case_name}]")
        wer = wer_results.get(case_name)
        semantic = semantic_results.get(case_name)
        if wer:
            print(f"WER:               {wer['wer']:.2%}")
            print(f"Word accuracy:     {wer['accuracy']:.2%}")
            print(f"Edit distance:     {wer['edit_distance']}")
        else:
            print("WER:               (missing pair)")
        if semantic:
            print(f"Semantic score:    {semantic['score']:.3f}")
            print(f"Interpretation:    {semantic['interpretation']}")
        else:
            print("Semantic score:    (missing pair)")
        print()


def run_all_tests(data_dir: Path | str | None = None, *, config: dict | None = None) -> tuple[dict, dict]:
    """Run WER + semantic over the benchmark dir, print a combined report, return raw dicts."""
    data_dir = Path(data_dir) if data_dir else default_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "references").mkdir(parents=True, exist_ok=True)
    (data_dir / "hypotheses").mkdir(parents=True, exist_ok=True)

    config = config or default_eval_config()

    print("[metrics] WER …", flush=True)
    t0 = time.perf_counter()
    wer_results = run_wer_on_dir(data_dir, config=config)
    print(f"[metrics] WER done in {time.perf_counter() - t0:.1f}s", flush=True)

    print("[metrics] semantic similarity (may load model on first run) …", flush=True)
    t1 = time.perf_counter()
    semantic_results = run_semantic_on_dir(data_dir, config=config)
    print(f"[metrics] semantic done in {time.perf_counter() - t1:.1f}s", flush=True)

    _print_report(wer_results, semantic_results)
    return wer_results, semantic_results


if __name__ == "__main__":
    run_all_tests()
