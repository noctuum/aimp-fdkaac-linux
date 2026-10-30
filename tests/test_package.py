import gzip
import tarfile
import zipfile
from pathlib import Path

from tools.pins import load_pins

ROOT = Path(__file__).resolve().parent.parent
PINS = load_pins(ROOT / "upstream.json")
DIST = ROOT / "dist"
PACKAGE = DIST / "enc_fdkaac.aimppack"
SOURCE = DIST / f"enc_fdkaac-{PINS.version}-src.tar.gz"
MEMBERS = [("enc_fdkaac/", 0o755), ("enc_fdkaac/LICENSE.fdk-aac.txt", 0o644), ("enc_fdkaac/LICENSE.fdkaac.txt", 0o644),
           ("enc_fdkaac/README.txt", 0o644), ("enc_fdkaac/enc_fdkaac.txt", 0o644), ("enc_fdkaac/x64/", 0o755),
           ("enc_fdkaac/x64/enc_fdkaac.xml", 0o644), ("enc_fdkaac/x64/fdkaac", 0o755), ("enc_fdkaac/x64/fdkaac-aimp", 0o755)]


def upstream_file(source_name, member_name):
    source = next(s for s in PINS.sources if s.name == source_name)
    with tarfile.open(ROOT / "third_party" / source.file) as t:
        member = next(m for m in t.getmembers() if m.name.split("/", 1)[-1] == member_name)
        return t.extractfile(member).read()


def test_aimppack_and_zip_are_the_same_bytes():
    assert PACKAGE.read_bytes() == (DIST / "enc_fdkaac.zip").read_bytes()


def test_layout_and_modes():
    with zipfile.ZipFile(PACKAGE) as z:
        assert [(i.filename, (i.external_attr >> 16) & 0o7777) for i in z.infolist()] == MEMBERS


def test_contents_match_their_sources():
    with zipfile.ZipFile(PACKAGE) as z:
        assert z.read("enc_fdkaac/x64/fdkaac") == (ROOT / "build/out/fdkaac").read_bytes()
        assert z.read("enc_fdkaac/x64/fdkaac-aimp") == (ROOT / "build/out/fdkaac-aimp").read_bytes()
        assert z.read("enc_fdkaac/x64/enc_fdkaac.xml") == (ROOT / "package/enc_fdkaac.xml").read_bytes()
        assert z.read("enc_fdkaac/LICENSE.fdkaac.txt") == upstream_file("fdkaac", "COPYING")
        assert z.read("enc_fdkaac/LICENSE.fdk-aac.txt") == upstream_file("fdk-aac", "NOTICE")


def test_source_archive_holds_the_exact_upstream_archives():
    top = f"enc_fdkaac-{PINS.version}-src"
    with tarfile.open(SOURCE) as t:
        names = t.getnames()
        assert names == sorted(names) and not any("__pycache__" in n for n in names)
        for path in ("build.sh", "upstream.json", "README.md", "scripts/container-build.sh", "scripts/pack.py", "wrapper/fdkaac-aimp.c"):
            assert f"{top}/{path}" in names, path
        for s in PINS.sources:
            data = t.extractfile(f"{top}/third_party/{s.file}").read()
            assert data == (ROOT / "third_party" / s.file).read_bytes()


def test_no_path_of_the_build_machine():
    marker = str(ROOT).encode()
    blobs = [PACKAGE.read_bytes(), gzip.decompress(SOURCE.read_bytes())]
    with zipfile.ZipFile(PACKAGE) as z:
        blobs += [z.read(i) for i in z.infolist() if not i.is_dir()]
    for blob in blobs:
        assert b"/home/" not in blob and marker not in blob
