import numpy as np
import pytest

from tests.helpers import MANIFEST, encode, first
from tools.m4a import decode
from tools.signals import tones
from tools.wavstream import AIMP_CHANNEL_MASKS, parse_wav

SPEAKERS = {0x1: "FL", 0x2: "FR", 0x4: "FC", 0x8: "LFE", 0x10: "BL", 0x20: "BR",
            0x40: "FLC", 0x80: "FRC", 0x200: "SL", 0x400: "SR"}
TONE = {"FL": 500, "FR": 600, "FC": 700, "LFE": 60, "BL": 800, "BR": 900,
        "SL": 1000, "SR": 1100, "FLC": 1200, "FRC": 1300}
SAME_AT_6 = {"BL": "SL", "BR": "SR"}


def speakers(mask):
    return [name for bit, name in sorted(SPEAKERS.items()) if mask & bit]


def dominant(samples, rate):
    spectrum = np.abs(np.fft.rfft(samples))
    return np.fft.rfftfreq(len(samples), 1 / rate)[np.argmax(spectrum)]


@pytest.mark.parametrize("channels", [6, 8])
def test_every_tone_stays_in_its_channel(fdkaac_bin, tmp_path, channels):
    rate, frames, names = 48000, 96000, speakers(AIMP_CHANNEL_MASKS[channels])
    role = (lambda n: SAME_AT_6.get(n, n)) if channels == 6 else (lambda n: n)
    out = tmp_path / "multi.m4a"
    pcm = tones(rate, channels, frames, [TONE[n] for n in names])
    assert encode(fdkaac_bin, first(MANIFEST.encoders[0]), rate, channels, frames, out, pcm=pcm).returncode == 0
    wav = parse_wav(decode(out))
    decoded = np.frombuffer(wav.data, "<i2").reshape(-1, channels)[8192:-8192]
    out_roles = [role(n) for n in speakers(wav.channel_mask)]
    for name in names:
        column = out_roles.index(role(name))
        assert abs(dominant(decoded[:, column], rate) - TONE[name]) < 5, (name, column)
