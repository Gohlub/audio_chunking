# Flow

The benchmark has four stages, each owned by a small module:

| Stage | Module | Reads | Writes |
|-------|--------|-------|--------|
| 1. **Prepare** | `datasets.<name>.prepare` | the corpus on the internet | `data/prepared/<name>/audio/raw/<case_id>.flac` + `data/prepared/benchmark/references/<case_id>.ref.txt` |
| 2. **Chunk** | `lib.chunking` | `audio/raw/<case_id>.flac` | `audio/chunked/<case_id>/part0001.{flac|wav|mp3}`, … (see `--chunk-format`) |
| 3. **Transcribe** | `lib.transcription` | the chunked parts | `data/prepared/benchmark/hypotheses/<case_id>.hyp.txt` |
| 4. **Tests** | `evaluation.tests` | matching `*.ref.txt` / `*.hyp.txt` pairs | WER + semantic similarity report |

`benchmark.py` runs all four stages end-to-end. Each stage is also runnable on its own.

## Setup

Fetch or provide these before running:

- `ffmpeg` / `ffprobe` on `PATH` for dataset normalization, duration probing,
  and chunk slicing (FLAC or WAV parts).
- Network access for dataset preparation. The default run downloads/prepares
  AMI, ICSI, and Earnings22 source data unless `--skip-prepare` is used.
- An STT provider API key before transcribing. Set `AQUAVOICE_API_KEY`
  (preferred) or `OPENAI_API_KEY`.
- Python dependencies via `uv`.

```bash
cd benchmark
uv venv
uv sync --project .
export OPENAI_API_KEY=...
```

## Run the full benchmark

```bash
uv run --project . benchmark.py                                           # all 3 datasets, defaults
uv run --project . benchmark.py ami                                       # one dataset
uv run --project . benchmark.py --chunk-seconds 300 --overlap-seconds 10  # default is 300s / 5 min (env STT_CHUNK_SECONDS)
uv run --project . benchmark.py --chunk-seconds 600 --overlap-seconds 10 # 10 min chunks if you prefer
uv run --project . benchmark.py --chunk-format wav                        # WAV chunks (e.g. if API rejects FLAC)
uv run --project . benchmark.py --chunk-format mp3                        # MP3 chunks (smaller than WAV; optional BENCHMARK_CHUNK_MP3_BITRATE)
uv run --project . benchmark.py --skip-prepare --skip-chunk --resume-transcribe   # resume transcription after crash
```

Prepare **does not** overwrite existing `*.hyp.txt` (only writes the `[placeholder: …]` stub when the file is missing). **`--resume-transcribe`** skips meetings whose hypothesis is already non-placeholder—combine with **`--skip-prepare`** and **`--skip-chunk`** to continue after a partial run without redoing **`EN2001a`** / **`ES2008a`** on AMI.

Default chunk length is **300 s** (5 minutes) with **10 s** overlap; override with **`--chunk-seconds`** / **`STT_CHUNK_SECONDS`** and **`--overlap-seconds`** / **`STT_OVERLAP_SECONDS`**.

Chunk files default to **FLAC** (`part*.flac`). Use **`--chunk-format wav`** or **`--chunk-format mp3`**, or env **`BENCHMARK_CHUNK_FORMAT`**, for **WAV** (`part*.wav`) or **MP3** (`part*.mp3`). MP3 uses **128 kb/s** mono at 16 kHz unless you set **`BENCHMARK_CHUNK_MP3_BITRATE`** (e.g. `96k`). Same overlap/length behavior for all formats.

Transient **`503`** / timeouts: transcription retries with exponential backoff ( **`BENCHMARK_TRANSCRIBE_MAX_RETRIES`** default `8`, **`BENCHMARK_TRANSCRIBE_RETRY_BASE_S`** default `4`, **`BENCHMARK_TRANSCRIBE_RETRY_CAP_S`** default `120`).

Default selection for `uv run --project . benchmark.py` (no dataset args):

- Datasets: `ami`, `icsi`, `earnings22`
- Default case IDs: `ami` -> `EN2001a`, `ES2008a`, `ES2008b`; `icsi` -> `Bmr001`, `Bns001`, `Bro003`; `earnings22` -> `4462231`, `4469528`

Prepared outputs are written under `data/prepared/<dataset>/...` and benchmark refs/hyps under `data/prepared/benchmark/{references,hypotheses}/`.


