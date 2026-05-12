# Long-form audio chunking for STT providers 

# Quickstart
Refer to [benchmark](benchmark/README.md) and [pipeline](pipeline/README.md) for further information.

Both entry points need a few non-Python dependencies:

- `ffmpeg` and `ffprobe` on `PATH` for audio normalization, duration probing, and chunk slicing.
- `uv` for Python dependency management.
- An STT provider API key before transcribing. The benchmark accepts `OPENAI_API_KEY`; the pipeline defaults to `OPENAI_API_KEY` for `avalon-1.5`.


To start the benchmark:

```bash
cd benchmark
uv venv
uv sync --project .
export OPENAI_API_KEY=...
```

```bash
uv run --project . benchmark.py                                           # all 3 datasets, defaults
uv run --project . benchmark.py ami                                       # one dataset
uv run --project . benchmark.py --chunk-seconds 300 --overlap-seconds 10  # optional; default is 300s (5 min)
uv run --project . benchmark.py --chunk-seconds 600 --overlap-seconds 10  # 10 min chunks
```

To start the ETL pipeline:

```bash
cd pipeline
uv sync
mkdir -p audio_files
export OPENAI_API_KEY=...
uv run python main.py
```

# Motivation
The motivation for this project originated in an OSS contribution I made some time ago ([PR #1889](https://github.com/cocoindex-io/cocoindex/pull/1889)) to CocoIndex, an AI-native ETL pipeline. My goal was to add STT as a first-class primitive to the core transformation offering, but I got an interesting comment on the issue I raised, specifically on [issue #1828](https://github.com/cocoindex-io/cocoindex/issues/1828#issuecomment-4239022518). In short, it came to my attention that STT model providers generally are subject to a certain set of constraints that were relevant to what I wanted to do. I opted in for an unopinionated API that extended the existing LiteLLM provider for embeddings (reasoning can be found [here](https://github.com/cocoindex-io/cocoindex/pull/1889#issue-4326648116)). In the context of CocoIndex specifically (which is specializing to be a 'context engine for your agents'), it is reasonable to assume that a *useful* STT transformation will generally need to support some type of long-form audio, so I leaned into that idea and decide to extend my work into a proper project.

---

# Outline
The project has two main components: `/benchmark` and `/pipeline`.

### Benchmark
The goal of the benchmark is to offer a common substrate for investigating different chunking strategies, and the benchmark is extensible to other datasets as well (see [Clanker.md](benchmark/datasets/CLANKER.md) for instructions). Currently, the benchmark supports 3 different corpora (AMI, ICSI and Earnings 22), which represent a good sample of what the the actual pipeline is built around (long-form, professional audio recordings).

### Pipeline
The pipeline itself is an amolgamation of the findings from the benchmark, in the form of an pipeline that inteligently chunks and transforms audio to text, and can act both as an intermediate step, or the whole processing pipeline itself (CocoIndex offers a myriad of source/target connectors: S3 buckets, Google Drive, databases, etc.).


# Results

End-to-end benchmark (`benchmark.py`): **Aquavoice `avalon-v1.5`**, overlaps merged with LCS stitching. Rows below reflect one **`evaluation/tests`** snapshot on the checked-in layout under `benchmark/data/prepared/benchmark/` (refs vs hyps). **Chunking differs by corpus** for this run: **AMI** and **Earnings22** kept hypotheses from earlier transcription (**300 s** segments, **10 s** overlap, **MP3**); **ICSI** was re-chunked and re-transcribed at **150 s / 10 s overlap / WAV** after provider timeouts on long MP3 uploads.

| Dataset | Case | Chunking (length / overlap / format) | WER | Word acc. | Edit distance | Semantic | Interpretation |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| earnings22 | 4462231 | 300 s / 10 s / MP3 | 18.43% | 81.57% | 1330 | 0.992 | Very similar meaning |
| earnings22 | 4469528 | 300 s / 10 s / MP3 | 22.71% | 77.29% | 844 | 0.883 | Mostly similar meaning |
| icsi | Bmr001 | 150 s / 10 s / WAV | 40.04% | 59.96% | 2565 | 0.882 | Mostly similar meaning |
| icsi | Bns001 | 150 s / 10 s / WAV | 29.80% | 70.20% | 4516 | 0.600 | Significant semantic difference |
| icsi | Bro003 | 150 s / 10 s / WAV | 25.50% | 74.50% | 3276 | 0.369 | Significant semantic difference |
| ami | EN2001a | 300 s / 10 s / MP3 | 18.39% | 81.61% | 2980 | 0.917 | Very similar meaning |
| ami | ES2008a | 300 s / 10 s / MP3 | 77.77% | 22.23% | 1963 | 0.316 | Significant semantic difference |
| ami | ES2008b | 300 s / 10 s / MP3 | 16.98% | 83.02% | 1022 | 0.973 | Very similar meaning |

Reproduce with [benchmark/README.md](benchmark/README.md); use `--resume-transcribe` with `--skip-chunk` when only some corpora need re-transcription.

# Discussion
In the spirit of scholarly diligence, I wanted to try as many different chunking strategies as possible. With some experimentation and deliberate thought, it struck me that the domain I wanted to focus on (professional audio) requires agressive/redundant context preservation, which meant that the strategy I want to go for most definitevely should involve some sort of chunking with overlapping, prompting me to produce the following table:

**API overhead (%):** extra audio volume across chunking strategies.

| Chunk **N** \ Overlap **M** | 5s | 10s | 15s | 20s | 30s |
| --- | ---: | ---: | ---: | ---: | ---: |
| 3 min (180s) | 5.56% | 11.11% | 16.67% | 22.22% | 33.33% |
| 5 min (300s) | 3.33% | 6.67% | 10.00% | 13.33% | 20.00% |
| 10 min (600s) | 1.67% | 3.33% | 5.00% | 6.67% | 10.00% |
| 15 min (900s) | 1.11% | 2.22% | 3.33% | 4.44% | 6.67% |
| 18 min (1080s) | 0.93% | 1.85% | 2.78% | 3.70% | 5.56% |

When overlapping **M** seconds on a timeline, each internal boundary is transcribed twice. Compared to sending the same timeline with **no overlap**, the steady-state **extra audio per chunk** relative to chunk length **N** is **(2M/N)×100**.

Now, observing the table above, one can exercise judgement as to what level of overhead is acceptible in a production environment. One tradeoff not obvious from this table is that, depending on the STT provider, transcription accuracy can degrade with longer chunks (context degradation). For my experiments, I found that 10:10 (3.33% overhead) and 15:10 (2.22%) was acceptable and enough to preserve context across the boundary. 

### Deduping transcripts
One small drawdown of the overlapping chunks strategy is that the resulting transcription will invariably include duplication that cannot be arbitraraly merged. For what appears to be a rare instance where Leetcode provided actual value to software development (joking), I opted for a longest common sequence algorithm to resolve duplications, and for fun, made a small animation (using [Manim](https://github.com/3b1b/manim)) to showcase how it works:

![](assets/AnimationScene.gif)

In principle, what happens is the following:
1. Slide subsequences of varying length across the adjecent chunks
2. During iteration, check for alignment (largest # positional of matches)
3. Merge along the (best) discovered subsequences (along the middle).
4. Win


### Hybrid chunking strategy
The default `hybrid` strategy for the pipeline:

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



## Notes
- You will notice that the benchmark makes no mention of [Silero VAD](https://github.com/snakers4/silero-vad). Due to the corpura metadata format, it was challenging to align transcripts with chunks (and hence evaluate the results), so I didn't benchmark the full strategy used by the pipeline. I opted in to use it because it the pipeline as it provides a form of pre-processing that can make the chunking strategy more informed (chunking at silence boundaries when it makes sense).

- For both the benchmark and the pipeline, I normalize the audio to 16 kHz mono FLAC, both in the interest of consistency in results and the free lossless compression.









