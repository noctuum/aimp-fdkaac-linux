"""Packs the add-on, the same bytes as a zip, and the source archive into a dist folder."""

import argparse
import gzip
import io
import shutil
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.aimppack import Member, write_zip  # noqa: E402
from tools.pins import Pins, load_pins  # noqa: E402

NAME = "enc_fdkaac"
SOURCE_FILES = ("build.sh", "upstream.json", "README.md")
SOURCE_DIRS = ("scripts", "tools", "wrapper", "package")
SOURCE_EXECUTABLES = ("build.sh", "scripts/container-build.sh")


def package_members(out: Path, sources: Path) -> list[Member]:
    top = f"{NAME}/"
    members = [
        Member(top, None, 0o755),
        Member(f"{top}LICENSE.fdk-aac.txt", sources / "fdk-aac" / "NOTICE", 0o644),
        Member(f"{top}LICENSE.fdkaac.txt", sources / "fdkaac" / "COPYING", 0o644),
        Member(f"{top}README.txt", ROOT / "package" / "README.txt", 0o644),
        Member(f"{top}enc_fdkaac.txt", ROOT / "package" / "enc_fdkaac.txt", 0o644),
        Member(f"{top}x64/", None, 0o755),
        Member(f"{top}x64/enc_fdkaac.xml", ROOT / "package" / "enc_fdkaac.xml", 0o644),
        Member(f"{top}x64/fdkaac", out / "fdkaac", 0o755),
        Member(f"{top}x64/fdkaac-aimp", out / "fdkaac-aimp", 0o755),
    ]
    return sorted(members, key=lambda m: m.arcname)


def source_files(pins: Pins) -> list[str]:
    files = list(SOURCE_FILES)
    for folder in SOURCE_DIRS:
        for path in (ROOT / folder).rglob("*"):
            rel = path.relative_to(ROOT)
            if path.is_file() and not any(p.startswith(".") or p == "__pycache__" for p in rel.parts):
                files.append(rel.as_posix())
    return files + [f"third_party/{s.file}" for s in pins.sources]


def write_source(dest: Path, top: str, files: list[str], epoch: int) -> None:
    folders = {top} | {f"{top}/{parent}" for f in files for parent in _parents(f)}
    entries = sorted([(name, None) for name in folders] + [(f"{top}/{f}", f) for f in files])
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as t:
        for name, rel in entries:
            # Fixed metadata, so the same tree gives the same bytes.
            info = tarfile.TarInfo(name)
            info.mtime, info.uid, info.gid, info.uname, info.gname = epoch, 0, 0, "", ""
            if rel is None:
                info.type, info.mode = tarfile.DIRTYPE, 0o755
                t.addfile(info)
            else:
                data = (ROOT / rel).read_bytes()
                info.size, info.mode = len(data), 0o755 if rel in SOURCE_EXECUTABLES else 0o644
                t.addfile(info, io.BytesIO(data))
    dest.write_bytes(gzip.compress(buf.getvalue(), compresslevel=9, mtime=0))


def _parents(rel: str) -> list[str]:
    parts = rel.split("/")[:-1]
    return ["/".join(parts[:i]) for i in range(1, len(parts) + 1)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Pack the add-on and its sources.")
    parser.add_argument("--out", type=Path, required=True, help="folder that holds fdkaac and fdkaac-aimp")
    parser.add_argument("--sources", type=Path, required=True, help="folder that holds the unpacked fdkaac and fdk-aac")
    parser.add_argument("--dist", type=Path, required=True, help="folder for the results")
    args = parser.parse_args()
    pins = load_pins(ROOT / "upstream.json")
    package = args.dist / f"{NAME}.aimppack"
    write_zip(package, package_members(args.out, args.sources), pins.source_date_epoch)
    shutil.copyfile(package, args.dist / f"{NAME}.zip")
    top = f"{NAME}-{pins.version}-src"
    write_source(args.dist / f"{top}.tar.gz", top, source_files(pins), pins.source_date_epoch)
    return 0


if __name__ == "__main__":
    sys.exit(main())
