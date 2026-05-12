# Clanker: pipe a new dataset into the benchmark pipeline

**Goal:** A prepare script downloads the corpus, normalises audio, and **materialises UTF-8 transcript pairs** that the evaluation layer can read. Downstream stages (chunking, transcription, scoring) are dataset-agnostic and pull from the standard layout below.

**Working directory for paths in this document:** the folder that contains `pyproject.toml`, `datasets/`, `pipeline/`, `data/`, `evaluation/`, `benchmark.py`.

---

## 1. Output contract

Your `prepare` step must produce all three of the following before the rest of the pipeline runs:

| Output | Path | Notes |
|--------|------|-------|
| **Raw audio (one per case)** | `data/prepared/<dataset_id>/audio/raw/<case_id>.flac` | 16 kHz mono FLAC. Written by `datasets.prepare.normalize_to_flac`. Source-of-truth for chunking and transcription. |
| **Reference transcript** | `data/prepared/benchmark/references/<case_id>.ref.txt` | UTF-8 plain text. Written by `datasets.prepare.write_benchmark_cases`. |
| **Hypothesis placeholder** | `data/prepared/benchmark/hypotheses/<case_id>.hyp.txt` | UTF-8. Same `write_benchmark_cases` writes a placeholder; the transcription step overwrites it later. |

`case_id` is a stable string usable as one path segment (e.g. `EN2001a`, `4462231`). The same `case_id` must appear in **all three** locations — the evaluator pairs `*.ref.txt` with `*.hyp.txt` by stem.

Path helpers in `datasets.prepare` (re-exported from `datasets.prepare.paths`): `raw_audio_dir(name)`, `raw_audio_path(name, case_id)`, `benchmark_references_dir()`, `benchmark_hypotheses_dir()`, `cache_dir(name)` (transient downloads, safe to wipe).

---

## 2. What *not* to do

- Do not assume the evaluator opens your audio. WER / semantic only read `*.ref.txt` / `*.hyp.txt`.
- Do not write FLAC anywhere other than `audio/raw/`. `chunking` reads from there.
- Do not use mismatched `case_id` values between a ref and its hyp. Stems must match exactly.
- If your reference text contains `A: ` / `B: ` style speaker prefixes, the evaluator strips those prefixes by default (`strip_speaker_labels` in `evaluation.tests`); turn it off when passing a custom ``config`` dict if plain text has no speaker labels.

---

## 3. Repository wiring (tasks for the agent)

1. **Add** `datasets/<dataset_id>/prepare.py` exposing `def main(argv: list[str] | None) -> int` and an Argparse CLI. It must:
   - download source media into `cache_dir(<id>)` (helper from `datasets.prepare`),
   - call `normalize_to_flac` (from `datasets.prepare`) to emit `audio/raw/<case_id>.flac` for each case,
   - expose a `DEFAULT_MEETINGS` / `DEFAULT_FILE_IDS` / `DEFAULT_CASE_IDS` tuple (`benchmark.py` reads these via `datasets.default_case_ids`).
2. **Add** `datasets/<dataset_id>/transcripts.py` that converts dataset-native annotations into `datasets.prepare.BenchmarkCase` records, then have `prepare.py` call `datasets.prepare.write_benchmark_cases(build_cases(...))`.
3. **Register** the dataset in `datasets/__init__.py` with one entry in `_DATASETS`. The dispatcher imports `datasets/<dataset_id>/prepare.py` by convention.
4. **Verify** (from the project root):
   - `uv run --project . data/prepare_dataset.py <dataset_id> -h` shows your CLI;
   - after a real prepare, `audio/raw/<case_id>.flac` and the `*.ref.txt` / `*.hyp.txt` pair exist for every case;
   - `uv run --project . evaluation/tests.py` does **not** print "No transcript pairs found".

**Reference implementations to mirror:** `datasets/ami/prepare.py` + `datasets/ami/transcripts.py`, or `datasets/earnings22/prepare.py` + `datasets/earnings22/transcripts.py` for a non-XML corpus.

---

## 4. Verification checklist

- [ ] `audio/raw/<case_id>.flac` exists for every case (16 kHz mono).
- [ ] `references/<case_id>.ref.txt` and `hypotheses/<case_id>.hyp.txt` exist for every case with matching `case_id` stems.
- [ ] `_DATASETS` in `datasets/__init__.py` lists the new id.
- [ ] `uv run --project . data/prepare_dataset.py list` includes the new id.
- [ ] `uv run --project . benchmark.py <dataset_id> --skip-prepare --skip-transcribe --skip-tests` chunks successfully.

This document is the single source of truth for **how the pipe connects** dataset preparation to chunking, transcription, and evaluation.
