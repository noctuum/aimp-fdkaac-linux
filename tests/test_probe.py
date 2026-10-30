import subprocess
from pathlib import Path

from tools.probereport import parse_report
from tools.wavstream import parse_wav, wav_header


def run(probe_bin, stdin, *args, report_dir=""):
    env = {"PATH": "/usr/bin:/bin", "PROBE_REPORT_DIR": str(report_dir)}
    return subprocess.run([probe_bin, *args], input=stdin, capture_output=True, timeout=30, env=env)


def report(out):
    return parse_report(Path(f"{out}.probe.txt").read_text(encoding="utf-8"))


def test_pcm_stream_with_zero_lengths(probe_bin, tmp_path):
    pcm, out, reports = bytes(range(256)) * 100, tmp_path / "out.wav", tmp_path / "reports"
    reports.mkdir()
    p = run(probe_bin, wav_header(44100, 2, 16) + pcm, "--id", "t1", "-o", str(out), "-", report_dir=reports)
    assert p.returncode == 0
    r = report(out)
    keys = ("state", "variant", "id", "format-tag", "channels", "sample-rate", "bits", "riff-size")
    assert [r.get(k) for k in keys] == ["done", "test", "t1", "0x0001", "2", "44100", "16", "0"]
    assert r.all("chunk") == ["fmt  16", "data 0"] and r.get("data-bytes") == str(len(pcm))
    assert r.get("header-hex") == wav_header(44100, 2, 16).hex()
    info = parse_wav(out.read_bytes())
    assert (info.data, info.data_size_field, info.riff_size_field) == (pcm, len(pcm), 36 + len(pcm))
    assert sorted(f.suffix for f in reports.iterdir()) == [".txt", ".wav"]


def test_extensible_six_channels(probe_bin, tmp_path):
    out = tmp_path / "six.wav"
    run(probe_bin, wav_header(48000, 6, 16, channel_mask=0x3F) + bytes(1200), "-o", str(out), "-")
    r = report(out)
    assert (r.get("format-tag"), r.get("channel-mask"), r.get("valid-bits")) == ("0xFFFE", "0x0000003F", "16")


def test_id3_tag_is_skipped(probe_bin, tmp_path):
    frame = b"TIT2" + (5).to_bytes(4, "big") + b"\0\0" + b"\3Test"
    tag = b"ID3\4\0\0" + len(frame).to_bytes(4, "big") + frame
    out = tmp_path / "id3.wav"
    run(probe_bin, tag + wav_header(44100, 2, 16) + bytes(400), "-o", str(out), "-")
    r = report(out)
    assert [r.get(k) for k in ("id3-size", "id3-frames", "riff", "data-bytes")] == [str(len(tag)), "TIT2", "RIFF", "400"]


def test_arguments_are_recorded_verbatim(probe_bin, tmp_path):
    out = tmp_path / "Папка с пробелами" / "Тест 01.wav"
    out.parent.mkdir()
    run(probe_bin, wav_header(44100, 2, 16), "--id", "06", "Тест с пробелами", "-o", str(out), "-")
    r = report(out)
    assert r.argv[1:] == ["--id", "06", "Тест с пробелами", "-o", str(out), "-"]
    assert r.get("output") == f"[{out}]" and out.exists()


def test_exit_code_and_chatter(probe_bin, tmp_path):
    out = tmp_path / "e.wav"
    p = run(probe_bin, wav_header(44100, 2, 16), "--exit", "3", "--chatter", "-o", str(out), "-")
    assert p.returncode == 3 and report(out).get("exit") == "3"
    assert p.stdout.decode().splitlines() == [f"probe: stdout line {i}" for i in (1, 2, 3)]
    assert p.stderr.decode().splitlines() == [f"probe: stderr line {i}" for i in (1, 2, 3)]


def test_discard_counts_without_writing_audio(probe_bin, tmp_path):
    out, reports = tmp_path / "d.wav", tmp_path / "reports"
    reports.mkdir()
    run(probe_bin, wav_header(44100, 2, 16) + bytes(1 << 20), "--discard", "-o", str(out), "-", report_dir=reports)
    assert report(out).get("data-bytes") == "1048576" and parse_wav(out.read_bytes()).data == b""
    assert [f.suffix for f in reports.iterdir()] == [".txt"]


def test_stream_without_riff_is_copied_raw(probe_bin, tmp_path):
    out = tmp_path / "raw.wav"
    run(probe_bin, b"garbage!" * 10, "-o", str(out), "-")
    assert report(out).get("riff") == "garb" and out.read_bytes() == b"garbage!" * 10
