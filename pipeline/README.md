## Pipeline

CocoIndex-based audio-to-text pipeline that scans local audio files, transcribes
them, and stores results in Postgres keyed by file path.

### Setup

Fetch or provide these before running:

- `ffmpeg` / `ffprobe` on `PATH` for audio probing and FLAC slicing.
- A running Postgres database. By default the pipeline connects to
  `postgres://cocoindex:cocoindex@localhost/cocoindex`; override with
  `POSTGRES_URL` if your database is elsewhere.
- Local audio files under `pipeline/audio_files/`, or set `PIPELINE_SOURCE_DIR`
  to the directory you want scanned.
- An STT provider API key supported by LiteLLM. For the default `avalon-1.5`
  model, set `OPENAI_API_KEY`.
- Python dependencies via `uv`; the first run may also fetch model weights used
  by Silero VAD.

```bash
cd pipeline
uv sync
mkdir -p audio_files
export OPENAI_API_KEY=...
uv run python main.py
```

### Environment variables

- `POSTGRES_URL` (default: `postgres://cocoindex:cocoindex@localhost/cocoindex`)
- `PIPELINE_TABLE_NAME` (default: `audio_transcriptions`)
- `PIPELINE_PG_SCHEMA` (default: `pipeline`)
- `PIPELINE_SOURCE_DIR` (default: `./audio_files`)
- `PIPELINE_TRANSCRIBER_MODEL` (default: `whisper-1`)
- `PIPELINE_VAD_SAMPLE_RATE` (default: `16000`)
- `PIPELINE_VAD_THRESHOLD` (default: `0.5`)
- `PIPELINE_AUDIO_PATTERNS` (comma-separated glob list; defaults include common audio formats)
- `PIPELINE_CHUNKING_STRATEGY` (`hybrid` | `overlap` | `silence`, default: `hybrid`)
- `PIPELINE_CHUNK_SECONDS` (maximum chunk length for `hybrid`, default: `600`)
- `PIPELINE_CHUNK_OVERLAP_SECONDS` (used by `overlap`; use `0` for contiguous windows with no overlap, default: `5`)
- `PIPELINE_CHUNK_MAX_DIRECT_BYTES` (direct-transcribe limit after FLAC conversion, default: `25000000`)
- `PIPELINE_CHUNK_MAX_DIRECT_SECONDS` (direct-transcribe duration limit, default: `1080`)
- `PIPELINE_CHUNK_HYBRID_SILENCE_MIN_DURATION` (long silence boundary for `hybrid`, default: `10`)
- `PIPELINE_CHUNK_SILENCE_THRESHOLD_DB` (used by `silence`, default: `-35`)
- `PIPELINE_CHUNK_SILENCE_MIN_DURATION` (used by `silence`, default: `0.5`)
- `PIPELINE_CHUNK_MIN_SECONDS` (drop tiny chunks, default: `0.2`)
- `PIPELINE_CHUNK_NORMALIZE_AUDIO` (apply loudness normalization while writing FLAC, default: `true`)

### Hybrid chunking strategy

The default `hybrid` strategy:

1. Checks whether the input can be reused. By default the pipeline writes a
   normalized 16 kHz mono FLAC; if normalization is disabled and the input is
   already 16 kHz mono FLAC, it can be reused without transcoding.
2. Runs Silero VAD over that prepared FLAC. If VAD detects no speech segments,
   the transcript is stored as an empty string and transcription is skipped.
3. Sends the prepared FLAC directly if it is under 25 MB and shorter than 18
   minutes.
4. Otherwise, uses VAD output to find natural silence boundaries of
   at least 10 seconds.
5. Splits greedily on those silence boundaries while keeping each chunk at most
   10 minutes.
6. Falls back to a 10-minute cut when no suitable silence boundary exists before
   the limit.

The memoized CocoIndex processing function includes the model name and full
chunking configuration as explicit dependencies, so changing normalization,
VAD, chunking, or direct-send limits invalidates cached transcripts.

### Requirements

- `ffmpeg` and `ffprobe` must be available on `PATH` for chunk slicing.

### Run

```bash
cd pipeline
uv run python main.py
```
