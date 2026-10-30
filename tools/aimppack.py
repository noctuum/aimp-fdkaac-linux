"""A zip writer that gives the same bytes for the same members."""

import stat
import time
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

_UNIX = 3
_MSDOS_DIRECTORY = 0x10


@dataclass(frozen=True)
class Member:
    arcname: str
    source: Path | None
    mode: int


def write_zip(dest: Path, members: Sequence[Member], timestamp: int) -> None:
    date_time = time.gmtime(timestamp)[:6]
    with zipfile.ZipFile(dest, "w") as z:
        for m in members:
            info = zipfile.ZipInfo(m.arcname, date_time)
            info.create_system = _UNIX
            if m.source is None:
                info.external_attr = (stat.S_IFDIR | m.mode) << 16 | _MSDOS_DIRECTORY
                z.writestr(info, b"", compress_type=zipfile.ZIP_STORED)
            else:
                info.external_attr = (stat.S_IFREG | m.mode) << 16
                z.writestr(info, m.source.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
