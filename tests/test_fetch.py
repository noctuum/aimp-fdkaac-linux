import gzip
import hashlib
import io
import json
import re
import tarfile
from pathlib import Path

from scripts.fetch import verify
from tools.pins import load_pins

ROOT = Path(__file__).resolve().parent.parent
COMMIT = "1b311f7cda11ddabc11bb0e6230506796a6018c5"


def archive(path, commit):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT, pax_headers={"comment": commit}) as t:
        info = tarfile.TarInfo("fdkaac-1.0.9/README")
        info.size = 1
        t.addfile(info, io.BytesIO(b"x"))
    path.write_bytes(gzip.compress(buf.getvalue(), mtime=0))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pins(tmp_path, sha256):
    data = json.loads((ROOT / "upstream.json").read_text())
    data["sources"] = [dict(data["sources"][0], sha256=sha256)]
    (tmp_path / "upstream.json").write_text(json.dumps(data))
    return load_pins(tmp_path / "upstream.json")


def test_matching_archive_passes(tmp_path):
    assert verify(pins(tmp_path, archive(tmp_path / "fdkaac-1.0.9.tar.gz", COMMIT)), tmp_path) == []


def test_wrong_hash_is_reported(tmp_path):
    archive(tmp_path / "fdkaac-1.0.9.tar.gz", COMMIT)
    assert any("sha256" in p for p in verify(pins(tmp_path, "0" * 64), tmp_path))


def test_wrong_commit_is_reported(tmp_path):
    sha = archive(tmp_path / "fdkaac-1.0.9.tar.gz", "f" * 40)
    assert any("commit" in p for p in verify(pins(tmp_path, sha), tmp_path))


def test_missing_archive_is_reported(tmp_path):
    assert any("missing" in p for p in verify(pins(tmp_path, "0" * 64), tmp_path))


def test_pins_are_complete():
    p = load_pins(ROOT / "upstream.json")
    assert all(re.fullmatch(r"[0-9a-f]{64}", s.sha256) and re.fullmatch(r"[0-9a-f]{40}", s.commit) for s in p.sources)
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", p.image_digest) and p.image_python.startswith("/opt/python/")
    assert p.version == "1.0.9"
