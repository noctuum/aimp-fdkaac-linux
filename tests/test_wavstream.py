import json
from pathlib import Path

import pytest

from tools.wavstream import aimp_wav_header, parse_wav, wav_header

HEADERS = json.loads((Path(__file__).parent / "fixtures/aimp-headers.json").read_text())


def test_pcm_header_has_zero_lengths():
    h = wav_header(44100, 2, 16)
    assert len(h) == 44 and h[:4] == b"RIFF" and h[8:16] == b"WAVEfmt "
    assert h[4:8] == h[40:44] == bytes(4)
    assert int.from_bytes(h[20:22], "little") == 1


def test_extensible_header_carries_the_mask():
    info = parse_wav(wav_header(48000, 6, 16, channel_mask=0x3F))
    assert (info.format_tag, info.channels, info.channel_mask, info.valid_bits) == (0xFFFE, 6, 0x3F, 16)


def test_float_header():
    info = parse_wav(wav_header(44100, 2, 32, float_samples=True))
    assert (info.format_tag, info.bits) == (3, 32)


def test_zero_data_size_reads_to_the_end():
    pcm = bytes(range(256)) * 4
    assert parse_wav(wav_header(44100, 2, 16) + pcm).data == pcm


@pytest.mark.parametrize("key", sorted(HEADERS))
def test_aimp_header_matches_the_probe(key):
    rate, channels = map(int, key.split("/"))
    assert aimp_wav_header(rate, channels).hex() == HEADERS[key]
