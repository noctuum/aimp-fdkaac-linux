"""Builds the probe kit in tmp/probe-kit: the probe variants, the add-on package and the test sources."""

import argparse
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.aimppack import Member, write_zip  # noqa: E402
from tools.manifest import load, problems  # noqa: E402

MANIFEST = ROOT / "probe/enc_probe.xml"
KIT = ROOT / "tmp/probe-kit"
BUILD = KIT / "build"
PACKAGE = KIT / "enc_probe"
REPORTS = KIT / "reports"
SOURCES = KIT / "Тестовые файлы"
LONG = KIT / "Длинный файл" / "25000 секунд.flac"
CFLAGS = ("-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-D_GNU_SOURCE")

VARIANTS = (
    ("probe_root", 0o755, "root"),
    ("probe_both", 0o755, "both-root"),
    ("probe_0644", 0o644, "mode-0644"),
    ("fdkaac", 0o755, "precedence"),
    ("x64/probe_both", 0o755, "both-x64"),
    ("x64/probe_x64", 0o755, "x64"),
)

CHANNELS = {"mono": 1, "stereo": 2, "quad": 4, "5.1": 6, "7.1": 8}
TONES = (220, 330, 440, 550, 660, 770, 880, 990)
HALF_SCALE = 0.5
PLUS_3_DBFS = 10 ** (3 / 20)
FLAC16 = ("-c:a", "flac", "-sample_fmt", "s16")
# The FLAC encoder of FFmpeg writes 24 bits per sample from s32 input.
FLAC24 = ("-c:a", "flac", "-sample_fmt", "s32")
SHORT = (
    ("01 Тест 16 бит 44100 Гц стерео.flac", FLAC16, 44100, "stereo", HALF_SCALE),
    ("02 Тест 24 бит 96000 Гц стерео.flac", FLAC24, 96000, "stereo", HALF_SCALE),
    ("03 Тест 32 бит целые 48000 Гц стерео.wav", ("-c:a", "pcm_s32le"), 48000, "stereo", HALF_SCALE),
    ("04 Тест 32 бит float 44100 Гц стерео.wav", ("-c:a", "pcm_f32le"), 44100, "stereo", PLUS_3_DBFS),
    ("05 Тест 16 бит 48000 Гц 5.1.flac", FLAC16, 48000, "5.1", HALF_SCALE),
    ("06 Тест 16 бит 48000 Гц 7.1.flac", FLAC16, 48000, "7.1", HALF_SCALE),
    ("07 Тест 16 бит 48000 Гц квадро.flac", FLAC16, 48000, "quad", HALF_SCALE),
    ("08 Тест 16 бит 44100 Гц моно.flac", FLAC16, 44100, "mono", HALF_SCALE),
    ("09 Тест 16 бит 8000 Гц моно.flac", FLAC16, 8000, "mono", HALF_SCALE),
    ("10 Тест 16 бит 192000 Гц стерео.flac", FLAC16, 192000, "stereo", HALF_SCALE),
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the probe kit in tmp/probe-kit.")
    parser.add_argument("--clean", action="store_true",
                        help="delete the reports of earlier runs and the long source before the build")
    args = parser.parse_args()
    if not args.clean and REPORTS.is_dir() and any(REPORTS.iterdir()):
        return fail(f"{rel(REPORTS)} holds reports of an earlier run: move them away, or run again with --clean")
    missing = [tool for tool in ("cc", "ffmpeg", "sox") if shutil.which(tool) is None]
    if missing:
        return fail(f"missing tools: {', '.join(missing)}")
    found = problems(load(MANIFEST))
    if found:
        return fail(f"{rel(MANIFEST)}: {'; '.join(found)}")
    try:
        clear(keep_long=not args.clean)
        REPORTS.mkdir(parents=True)
        compile_variants()
        write_package()
        write_sources()
        write_long_source()
    except subprocess.CalledProcessError as e:
        return fail(f"exit code {e.returncode} from {shlex.join(e.cmd)}")
    step(f"done: {rel(KIT)}")
    return 0


def fail(message: str) -> int:
    print(f"make_kit: {message}", file=sys.stderr)
    return 1


def step(message: str) -> None:
    print(message, flush=True)


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def run(*cmd) -> None:
    subprocess.run([str(c) for c in cmd], check=True)


def clear(keep_long: bool) -> None:
    if not KIT.exists():
        return
    keep = keep_long and LONG.exists()
    step(f"clearing {rel(KIT)}" + (f", keeping {rel(LONG)}" if keep else ""))
    for path in KIT.iterdir():
        if keep and path == LONG.parent:
            for p in path.iterdir():
                if p != LONG:
                    remove(p)
        else:
            remove(path)


def remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def compile_variants() -> None:
    BUILD.mkdir()
    for _, _, variant in VARIANTS:
        step(f"compiling the probe variant {variant}")
        run("cc", *CFLAGS, f"-DPROBE_VARIANT={c_string(variant)}", f"-DPROBE_REPORT_DIR={c_string(str(REPORTS))}",
            "-o", BUILD / variant, ROOT / "probe/probe.c")


def c_string(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def write_package() -> None:
    step(f"writing {rel(PACKAGE)}")
    (PACKAGE / "x64").mkdir(parents=True)
    shutil.copyfile(MANIFEST, PACKAGE / "enc_probe.xml")
    modes = {PACKAGE: 0o755, PACKAGE / "x64": 0o755, PACKAGE / "enc_probe.xml": 0o644}
    for member, mode, variant in VARIANTS:
        shutil.copyfile(BUILD / variant, PACKAGE / member)
        modes[PACKAGE / member] = mode
    members = []
    for path, mode in modes.items():
        path.chmod(mode)
        name = path.relative_to(KIT).as_posix()
        members.append(Member(f"{name}/", None, mode) if path.is_dir() else Member(name, path, mode))
    step(f"writing {rel(KIT / 'enc_probe.aimppack')}")
    write_zip(KIT / "enc_probe.aimppack", sorted(members, key=lambda m: m.arcname), int(time.time()))


def write_sources() -> None:
    SOURCES.mkdir()
    for name, codec, rate, layout, amplitude in SHORT:
        step(f"writing {rel(SOURCES / name)}")
        exprs = "|".join(f"{amplitude}*sin(2*PI*{tone}*t)" for tone in TONES[:CHANNELS[layout]])
        tags = () if name.endswith(".wav") else flac_tags(name)
        run("ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i", f"aevalsrc=exprs={exprs}:c={layout}:s={rate}:d=3",
            *codec, *tags, SOURCES / name)


def flac_tags(name: str) -> tuple[str, ...]:
    number, title = name.removesuffix(".flac").split(" ", 1)
    return ("-metadata", f"TITLE={title}", "-metadata", "ARTIST=Зонд", "-metadata", "ALBUM=Набор зонда",
            "-metadata", f"TRACKNUMBER={int(number)}")


def write_long_source() -> None:
    if LONG.exists():
        return
    LONG.parent.mkdir(exist_ok=True)
    part = LONG.with_name(LONG.name + ".part")
    step(f"writing {rel(LONG)}, about two minutes")
    # Without dither every sample holds the same value, which FLAC stores in a few megabytes.
    run("sox", "-D", "-n", "-r", "44100", "-b", "16", "-c", "2", "-t", "flac", part,
        "synth", "25000", "sine", "0", "dcshift", "0.01")
    part.rename(LONG)


if __name__ == "__main__":
    sys.exit(main())
