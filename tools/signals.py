"""Test signals: 16-bit PCM with one sine tone per channel."""

from collections.abc import Sequence

import numpy as np


def tones(rate: int, channels: int, frames: int, freqs: Sequence[float] | None = None,
          amplitude: float = 0.25) -> bytes:
    if freqs is None:
        freqs = [440 + 110 * k for k in range(channels)]
    t = np.arange(frames) / rate
    pcm = np.stack([np.sin(2 * np.pi * f * t) for f in freqs], axis=1) * (amplitude * 32767)
    return np.round(pcm).astype("<i2").tobytes()
