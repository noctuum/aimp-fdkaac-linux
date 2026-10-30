"""The manifest under test, one encode the way AIMP runs it, and the checks every output passes."""

import os
import subprocess
from fractions import Fraction
from pathlib import Path

from tools.manifest import argv, expand, load
from tools.signals import tones
from tools.wavstream import aimp_wav_header

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = load(ROOT / os.environ.get("ENC_MANIFEST", "package/enc_fdkaac.xml"))
EXPECTED_PROFILE = {"2": "LC", "5": "HE-AAC", "29": "HE-AACv2"}


def first(encoder):
    return expand(encoder.presets[0])[0]


def encode(fdkaac_bin, combo, rate, channels, frames, out, pcm=None):
    data = aimp_wav_header(rate, channels) + (tones(rate, channels, frames) if pcm is None else pcm)
    return subprocess.run([str(fdkaac_bin), *argv(combo.cmdline, str(out))], input=data, capture_output=True)


def check(info, combo, rate, channels, frames):
    args = argv(combo.cmdline, "OUT")
    assert info.profile == EXPECTED_PROFILE[args[args.index("-p") + 1] if "-p" in args else "2"]
    # fdkaac signals SBR and no PS in mono HE-AAC, and FFmpeg reports such a stream as stereo.
    reported = 2 if info.profile == "HE-AAC" and channels == 1 else channels
    assert (info.sample_rate, info.channels) == (rate, reported)
    assert info.encoder.startswith("fdkaac 1.0.9, libfdk-aac ")
    assert info.smpb is not None and info.smpb.length * info.time_base == Fraction(frames, rate)
    assert info.smpb.delay + info.smpb.length + info.smpb.padding == info.duration_ts
