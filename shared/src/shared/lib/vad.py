"""
Silero VAD wrapper.

Given a path to audio, return a list of speech segments
``[{"start": float, "end": float}, …]`` in seconds (audio is resampled for Silero; default
16 kHz mono). No file writing — callers can use this to gate transcription or to pick chunk
boundaries.

Heavy deps (``torch``, ``silero_vad``, ``torchaudio``, ``scipy``) are imported lazily so importing
this module is cheap.
"""
from __future__ import annotations

from pathlib import Path

_model = None


def _silero_model():
    global _model
    if _model is None:
        from silero_vad import load_silero_vad

        _model = load_silero_vad()
    return _model


def _load_mono(path: Path, target_sr_hz: int):
    """Load audio as a 1-D float tensor at ``target_sr_hz`` mono."""
    import numpy as np
    import torch
    import torchaudio

    waveform, sample_rate = torchaudio.load(str(path))
    if waveform.ndim == 2 and waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0, keepdim=True)
    if sample_rate != target_sr_hz:
        waveform = torchaudio.transforms.Resample(sample_rate, target_sr_hz)(waveform)
    return waveform.squeeze(0).to(dtype=torch.float32).numpy().astype(np.float32)


def speech_segments(
    path: Path | str,
    *,
    threshold: float = 0.5,
    sampling_rate: int = 16_000,
) -> list[dict[str, float]]:
    """
    Return Silero VAD speech segments (seconds) for ``path``.

    Each segment is ``{"start": <s>, "end": <s>}``. Empty list if no speech is detected.

    ``threshold`` is passed to Silero (speech probability cutoff). ``sampling_rate`` must be
    a rate supported by the bundled Silero model (typically 8000 or 16000 Hz).
    """
    import torch
    from silero_vad import get_speech_timestamps

    audio = _load_mono(Path(path), sampling_rate)
    return get_speech_timestamps(
        torch.from_numpy(audio),
        _silero_model(),
        threshold=threshold,
        sampling_rate=sampling_rate,
        return_seconds=True,
    )
