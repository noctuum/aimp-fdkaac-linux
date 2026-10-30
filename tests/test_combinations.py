import subprocess
import threading

import pytest

from tests.helpers import MANIFEST, check, encode, first
from tools.m4a import stream_info
from tools.manifest import argv, expand
from tools.signals import tones
from tools.wavstream import aimp_wav_header

CASES = [(e, c, rate, ch) for e in MANIFEST.encoders for p in e.presets for c in expand(p)
         for rate in e.formats.sample_rates for ch in e.formats.channels]


def case_id(case):
    e, c, rate, ch = case
    return f"{e.name}/{c.preset}/{'+'.join(v for _, v in c.choices) or '-'}/{rate}/{ch}ch"


@pytest.mark.parametrize("case", CASES, ids=case_id)
def test_combination(fdkaac_bin, tmp_path, case):
    e, combo, rate, channels = case
    out = tmp_path / "out.m4a"
    p = encode(fdkaac_bin, combo, rate, channels, rate, out)
    assert p.returncode == 0, p.stderr.decode()
    check(stream_info(out), combo, rate, channels, rate)


def test_output_path_with_spaces_and_cyrillic(fdkaac_bin, tmp_path):
    folder = tmp_path / "Папка с пробелами"
    folder.mkdir()
    for e in MANIFEST.encoders:
        out = folder / f"01 Тест {e.name}.m4a"
        assert encode(fdkaac_bin, first(e), 44100, 2, 44100, out).returncode == 0 and out.exists()


@pytest.mark.parametrize("frames", [0, 2, 2048])
def test_short_input(fdkaac_bin, tmp_path, frames):
    for e in MANIFEST.encoders:
        out = tmp_path / f"{e.name}-{frames}.m4a"
        assert encode(fdkaac_bin, first(e), 44100, 2, frames, out).returncode == 0
        check(stream_info(out), first(e), 44100, 2, frames)


@pytest.mark.slow
def test_more_than_4_gib_through_the_pipe(fdkaac_bin, tmp_path):
    rate, seconds, out = 44100, 25000, tmp_path / "long.m4a"
    combo = first(MANIFEST.encoders[0])
    p = subprocess.Popen([fdkaac_bin, *argv(combo.cmdline, str(out))], stdin=subprocess.PIPE)
    block = tones(rate, 2, rate)

    def feed():
        p.stdin.write(aimp_wav_header(rate, 2))
        for _ in range(seconds):
            p.stdin.write(block)
        p.stdin.close()

    threading.Thread(target=feed).start()
    assert p.wait(timeout=1800) == 0
    check(stream_info(out), combo, rate, 2, rate * seconds)
