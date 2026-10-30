"""Reads upstream.json: the pinned upstream archives, the build image and the package version."""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Source:
    name: str
    version: str
    tag: str
    commit: str
    url: str
    file: str
    sha256: str


@dataclass(frozen=True)
class Pins:
    package_revision: int
    source_date_epoch: int
    sources: tuple[Source, ...]
    image: str
    image_digest: str
    image_python: str

    @property
    def version(self) -> str:
        base = next(s.version for s in self.sources if s.name == "fdkaac")
        return base if self.package_revision == 0 else f"{base}-{self.package_revision}"

    @property
    def image_ref(self) -> str:
        return f"{self.image}@{self.image_digest}"


def load_pins(path: Path) -> Pins:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    image = data["image"]
    return Pins(
        package_revision=int(data["package_revision"]),
        source_date_epoch=int(data["source_date_epoch"]),
        sources=tuple(Source(**s) for s in data["sources"]),
        image=image["name"],
        image_digest=image["digest"],
        image_python=image["python"],
    )
