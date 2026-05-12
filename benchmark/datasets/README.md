# Datasets

The benchmark currently runs against three meeting / long-form speech corpora. Each one is a
small Python subpackage under this folder (`prepare.py` + `transcripts.py`); the prepare script
downloads the source media, normalises audio to 16 kHz mono FLAC, and writes a reference
transcript that the evaluator can pair against the ASR output.

For the *mechanics* of plugging a new corpus into the pipeline, see [CLANKER.md](CLANKER.md).
This document is a higher-level description of what each registered dataset actually is.

| Id | Source | Default cases | License |
|----|--------|---------------|---------|
| `ami` | [Link](https://groups.inf.ed.ac.uk/ami/download/) | `EN2001a`, `ES2008a`, `ES2008b` | TODO |
| `icsi` |[Link](https://groups.inf.ed.ac.uk/ami/icsi/download/#) | `Bmr001`, `Bns001`, `Bro003` | TODO |
| `earnings22` | [Link](https://github.com/revdotcom/speech-datasets) | `4462231`, `4469528` | TODO |

---

## AMI

**What it is.** Multimodal dataset with 100 hours of prompted and unprompted meetings, default cases were semi-randomly chosen (criteria was length).

**Audio used by the benchmark.** Mix-Headset WAV, downmixed to 16 kHz mono FLAC.

**Reference transcripts.** Manual word-level NXT XML, parsed by `datasets.prepare.word_xml`. AMI
marks punctuation tokens with `punc="true"`; everything else is treated as a spoken token.

**Default cases.** `EN2001a`, `ES2008a`, `ES2008b`. Override on the CLI:
`prepare_dataset.py ami EN2001a EN2001b …`.

## ICSI

**What it is.** Multimodal dataset around 70 hours of prompted and unprompted meetings, more focus on professional/technical topics.


**Audio used by the benchmark.** Single-channel "interaction" WAV per meeting, downmixed to
16 kHz mono FLAC.

**Reference transcripts.** Manual NXT word XML (same parser as AMI). ICSI does *not* use the
`punc="true"` attribute — punctuation is identified by the `c="…"` class attribute.

**Default cases.** `Bmr001`, `Bns001`, `Bro003`.

**Notes / gotchas.** Audio mirror and annotation zip URL can be overridden via
`--audio-mirror` / `--annot-zip-url` (or env `ICSI_AUDIO_MIRROR_URL` / `ICSI_ANNOT_ZIP_URL`).
The annotation zip unpacks to `ICSI/Words/`; the prepare script renames it to `words/` so the
shared parser can find it.

---

## earnings22

**What it is.** Multimodal dataset of ~119 hours of earning calls across different languages, focus on technical topics.


**Audio used by the benchmark.** Per-call MP3, decoded to 16 kHz mono FLAC. The MP3 lives in
Git LFS — the prepare script pulls from `github.com/<u>/<r>/raw/…`.

**Reference transcripts.** Rev's `.nlp` files (`|`-delimited rows of
`token|speaker|ts|endTs|punctuation|case|tags|wer_tags`), reconstructed into a flat surface
string by `datasets/earnings22/transcripts.py`. Pass `--aligned-nlp` to use
`force_aligned_nlp_references/<id>.aligned.nlp` instead.

**Default cases.** `4462231`, `4469528` (file IDs from Rev's `metadata.csv`). Override with
positional args or env `EARNINGS22_FILE_IDS=<id1>,<id2>`.

**Notes / gotchas.** TODO.
