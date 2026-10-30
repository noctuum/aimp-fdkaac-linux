"""Prints the reports of the probe encoder as the rows of a Markdown table."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.probereport import parse_report  # noqa: E402

COLUMNS = ("report", "id", "variant", "state", "output", "format-tag", "channels", "channel-mask", "sample-rate",
           "bits", "riff-size", "data size field", "data-bytes", "exit", "fd1", "fd2")


def row(path: Path) -> list[str]:
    r = parse_report(path.read_text(encoding="utf-8", errors="replace"))
    data = [v.split(" ", 1)[1] for v in r.all("chunk") if v.startswith("data ")]
    own = {"report": path.stem, "data size field": data[0] if data else None}
    return [own.get(c) or r.get(c) or "-" for c in COLUMNS]


def main() -> int:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "tmp/probe-kit/reports"
    if not folder.is_dir():
        print(f"summarize: {folder} is not a directory", file=sys.stderr)
        return 1
    print("| " + " | ".join(COLUMNS) + " |")
    print("|" + "---|" * len(COLUMNS))
    for path in sorted(folder.glob("*.txt")):
        print("| " + " | ".join(cell.replace("|", "\\|") for cell in row(path)) + " |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
