"""Downloads and verifies the pinned upstream archives of upstream.json."""

import argparse
import hashlib
import sys
import tarfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.pins import Pins, Source, load_pins  # noqa: E402

PINS = ROOT / "upstream.json"
THIRD_PARTY = ROOT / "third_party"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def archive_commit(path: Path) -> str | None:
    # git archive, which serves the tag archives of GitHub, writes the commit into the pax global header.
    with tarfile.open(path, "r:gz") as t:
        return t.pax_headers.get("comment")


def verify(pins: Pins, third_party: Path) -> list[str]:
    problems = []
    for s in pins.sources:
        path = third_party / s.file
        if not path.is_file():
            problems.append(f"{s.file}: missing")
            continue
        digest = sha256(path)
        if digest != s.sha256:
            problems.append(f"{s.file}: sha256 {digest}, pinned {s.sha256 or '(empty)'}")
        commit = archive_commit(path)
        if commit != s.commit:
            problems.append(f"{s.file}: commit {commit} in the pax header, pinned {s.commit}")
    return problems


def download(source: Source, third_party: Path) -> Path:
    third_party.mkdir(exist_ok=True)
    dest = third_party / source.file
    if dest.exists():
        raise FileExistsError(f"{dest.name} exists in {third_party.name}/")
    part = dest.with_name(dest.name + ".part")
    with urllib.request.urlopen(source.url, timeout=60) as r, open(part, "xb") as f:
        while block := r.read(1 << 20):
            f.write(block)
    part.rename(dest)
    print(f"{source.file}: sha256 {sha256(dest)}, commit {archive_commit(dest)}")
    return dest


def main() -> int:
    parser = argparse.ArgumentParser(description="Download and verify the pinned upstream archives.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--verify", action="store_true", help="check the archives in third_party/ against upstream.json")
    group.add_argument("--download", metavar="NAME", help="download the archive of one source into third_party/")
    group.add_argument("--print", choices=("image_ref", "epoch", "version", "python"), help="print one pinned value")
    args = parser.parse_args()
    pins = load_pins(PINS)
    if args.print:
        values = {"image_ref": pins.image_ref, "epoch": pins.source_date_epoch, "version": pins.version,
                  "python": pins.image_python}
        print(values[args.print])
        return 0
    if args.download:
        source = next((s for s in pins.sources if s.name == args.download), None)
        if source is None:
            print(f"fetch: no source named {args.download}", file=sys.stderr)
            return 1
        try:
            download(source, THIRD_PARTY)
        except (FileExistsError, OSError, urllib.error.URLError) as e:
            print(f"fetch: {source.name}: {e}", file=sys.stderr)
            return 1
        return 0
    problems = verify(pins, THIRD_PARTY)
    for p in problems:
        print(f"fetch: {p}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
