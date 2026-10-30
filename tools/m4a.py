"""What fdkaac wrote, read back with FFmpeg: stream parameters, gapless info, AAC payload and PCM."""

import json
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path


@dataclass(frozen=True)
class Smpb:
    delay: int
    padding: int
    length: int


@dataclass(frozen=True)
class StreamInfo:
    profile: str | None
    sample_rate: int
    channels: int
    time_base: Fraction
    duration_ts: int | None
    encoder: str
    smpb: Smpb | None


def parse_smpb(value: str) -> Smpb:
    # iTunSMPB holds hex fields: a zero, the delay, the padding, then the length in samples.
    fields = value.split()
    return Smpb(delay=int(fields[1], 16), padding=int(fields[2], 16), length=int(fields[3], 16))


def stream_info(path: Path) -> StreamInfo:
    data = json.loads(_run("ffprobe", "-v", "error", "-of", "json", "-show_streams", "-show_format", str(path)))
    stream = next(s for s in data["streams"] if s.get("codec_type") == "audio")
    tags = {k.lower(): v for k, v in data["format"].get("tags", {}).items()}
    smpb = tags.get("itunsmpb")
    return StreamInfo(stream.get("profile"), int(stream["sample_rate"]), stream["channels"],
                      Fraction(stream["time_base"]), stream.get("duration_ts"),
                      tags.get("encoder", ""), parse_smpb(smpb) if smpb else None)


def aac_payload(path: Path) -> bytes:
    return _run("ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a", "-c", "copy", "-f", "data", "-")


def decode(path: Path) -> bytes:
    # The native decoder of FFmpeg, so the check does not decode with the library it tests.
    return _run("ffmpeg", "-v", "error", "-c:a", "aac", "-i", str(path), "-c:a", "pcm_s16le", "-f", "wav", "-")


def _run(*cmd: str) -> bytes:
    p = subprocess.run(cmd, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(f"{cmd[0]} exited with {p.returncode}: {p.stderr.decode(errors='replace').strip()}")
    return p.stdout
