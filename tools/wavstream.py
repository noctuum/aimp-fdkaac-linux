"""WAV headers and a WAV parser for the tests and the probe kit."""

import struct
import uuid
from dataclasses import dataclass

WAVE_FORMAT_PCM = 0x0001
WAVE_FORMAT_IEEE_FLOAT = 0x0003
WAVE_FORMAT_EXTENSIBLE = 0xFFFE


@dataclass(frozen=True)
class WavInfo:
    format_tag: int
    channels: int
    sample_rate: int
    bits: int
    valid_bits: int | None
    channel_mask: int | None
    riff_size_field: int
    data_size_field: int
    data: bytes


def _subformat(tag: int) -> bytes:
    return uuid.UUID(f"{tag:08x}-0000-0010-8000-00aa00389b71").bytes_le


def wav_header(rate: int, channels: int, bits: int, *, float_samples: bool = False,
               channel_mask: int | None = None, riff_size: int = 0, data_size: int = 0) -> bytes:
    tag = WAVE_FORMAT_IEEE_FLOAT if float_samples else WAVE_FORMAT_PCM
    block_align = channels * bits // 8
    if channel_mask is None:
        fmt = struct.pack("<HHIIHH", tag, channels, rate, rate * block_align, block_align, bits)
    else:
        fmt = struct.pack("<HHIIHH", WAVE_FORMAT_EXTENSIBLE, channels, rate, rate * block_align, block_align, bits)
        fmt += struct.pack("<HHI", 22, bits, channel_mask) + _subformat(tag)
    return (b"RIFF" + struct.pack("<I", riff_size) + b"WAVE"
            + b"fmt " + struct.pack("<I", len(fmt)) + fmt
            + b"data" + struct.pack("<I", data_size))


def parse_wav(data: bytes) -> WavInfo:
    if data[:4] not in (b"RIFF", b"RF64"):
        raise ValueError("no RIFF header")
    if data[8:12] != b"WAVE":
        raise ValueError("no WAVE form type")
    riff_size = int.from_bytes(data[4:8], "little")
    fmt = None
    pos = 12
    while pos + 8 <= len(data):
        chunk_id = data[pos:pos + 4]
        size = int.from_bytes(data[pos + 4:pos + 8], "little")
        body = pos + 8
        if chunk_id == b"data":
            if fmt is None:
                raise ValueError("no fmt chunk before the data chunk")
            end = len(data) if size == 0 or size > len(data) - body else body + size
            return _info(fmt, riff_size, size, data[body:end])
        if chunk_id == b"fmt ":
            fmt = data[body:body + size]
            if len(fmt) < 16:
                raise ValueError("fmt chunk shorter than 16 bytes")
        pos = body + size + (size & 1)
    raise ValueError("no fmt chunk" if fmt is None else "no data chunk")


def _info(fmt: bytes, riff_size: int, data_size: int, payload: bytes) -> WavInfo:
    tag, channels, rate, _, _, bits = struct.unpack("<HHIIHH", fmt[:16])
    valid_bits = mask = None
    if tag == WAVE_FORMAT_EXTENSIBLE and len(fmt) >= 24:
        _, valid_bits, mask = struct.unpack("<HHI", fmt[16:24])
    return WavInfo(tag, channels, rate, bits, valid_bits, mask, riff_size, data_size, payload)
