import json
import shutil
import subprocess
import zipfile
from pathlib import Path

from tools.manifest import load, problems
from tools.probereport import parse_report

ROOT = Path(__file__).resolve().parent.parent
MEMBERS = [("enc_probe/", 0o755), ("enc_probe/enc_probe.xml", 0o644), ("enc_probe/fdkaac", 0o755),
           ("enc_probe/probe_0644", 0o644), ("enc_probe/probe_both", 0o755), ("enc_probe/probe_root", 0o755),
           ("enc_probe/x64/", 0o755), ("enc_probe/x64/probe_both", 0o755), ("enc_probe/x64/probe_x64", 0o755)]
VARIANTS = {"fdkaac": "precedence", "probe_0644": "mode-0644", "probe_both": "both-root",
            "probe_root": "root", "x64/probe_both": "both-x64", "x64/probe_x64": "x64"}
SOURCES = {
    "01 Тест 16 бит 44100 Гц стерео.flac": ("flac", 44100, 2, 16),
    "02 Тест 24 бит 96000 Гц стерео.flac": ("flac", 96000, 2, 24),
    "03 Тест 32 бит целые 48000 Гц стерео.wav": ("pcm_s32le", 48000, 2, 32),
    "04 Тест 32 бит float 44100 Гц стерео.wav": ("pcm_f32le", 44100, 2, 32),
    "05 Тест 16 бит 48000 Гц 5.1.flac": ("flac", 48000, 6, 16),
    "06 Тест 16 бит 48000 Гц 7.1.flac": ("flac", 48000, 8, 16),
    "07 Тест 16 бит 48000 Гц квадро.flac": ("flac", 48000, 4, 16),
    "08 Тест 16 бит 44100 Гц моно.flac": ("flac", 44100, 1, 16),
    "09 Тест 16 бит 8000 Гц моно.flac": ("flac", 8000, 1, 16),
    "10 Тест 16 бит 192000 Гц стерео.flac": ("flac", 192000, 2, 16),
}


def stream(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-of", "json", "-show_streams", "-show_format", path],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def test_probe_manifest_is_valid():
    m = load(ROOT / "probe/enc_probe.xml")
    assert problems(m) == [] and len(m.encoders) == 17


def test_every_app_is_in_the_package():
    names = {n for n, _ in MEMBERS}
    for e in load(ROOT / "probe/enc_probe.xml").encoders:
        stem = e.app.removesuffix(".exe")
        assert {f"enc_probe/{stem}", f"enc_probe/x64/{stem}"} & names, e.app


def test_package_layout_and_modes(kit):
    with zipfile.ZipFile(kit / "enc_probe.aimppack") as z:
        assert [(i.filename, (i.external_attr >> 16) & 0o7777) for i in z.infolist()] == MEMBERS


def test_variants_name_themselves(kit, tmp_path):
    for member, variant in VARIANTS.items():
        exe = tmp_path / variant
        shutil.copy(kit / "enc_probe" / member, exe)
        exe.chmod(0o755)
        out = tmp_path / f"{variant}.wav"
        subprocess.run([exe, "-o", str(out)], input=b"", timeout=30, env={"PROBE_REPORT_DIR": ""})
        assert parse_report(Path(f"{out}.probe.txt").read_text()).get("variant") == variant


def test_sources_have_the_listed_formats(kit):
    for name, expected in SOURCES.items():
        s = stream(kit / "Тестовые файлы" / name)["streams"][0]
        bits = int(s.get("bits_per_raw_sample") or s["bits_per_sample"])
        assert (s["codec_name"], int(s["sample_rate"]), s["channels"], bits) == expected, name


def test_long_source_holds_more_than_4_gib_of_pcm(kit):
    info = stream(kit / "Длинный файл" / "25000 секунд.flac")
    assert round(float(info["format"]["duration"])) * 44100 * 2 * 2 > 2**32


def test_summary_has_a_row_per_report(probe_bin, tmp_path):
    outputs, reports = tmp_path / "out", tmp_path / "reports"
    outputs.mkdir()
    reports.mkdir()
    for i in ("a1", "b2"):
        subprocess.run([probe_bin, "--id", i, "-o", str(outputs / f"{i}.wav")], input=b"", timeout=30,
                       env={"PROBE_REPORT_DIR": str(reports)})
    table = subprocess.run(["python3", "-I", ROOT / "probe/summarize.py", reports],
                           capture_output=True, text=True, check=True).stdout
    assert sum(" a1 " in line or " b2 " in line for line in table.splitlines()) == 2
