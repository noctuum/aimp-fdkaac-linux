"""Parser for the reports of the probe encoder."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Report:
    lines: tuple[tuple[str, str], ...]

    def get(self, key: str) -> str | None:
        return next((value for k, value in self.lines if k == key), None)

    def all(self, key: str) -> list[str]:
        return [value for k, value in self.lines if k == key]

    @property
    def argv(self) -> list[str]:
        indexed = [(int(k[5:-1]), v) for k, v in self.lines if k.startswith("argv[") and k.endswith("]")]
        return [_strip_brackets(v) for _, v in sorted(indexed)]


def _strip_brackets(value: str) -> str:
    if len(value) >= 2 and value[0] == "[" and value[-1] == "]":
        return value[1:-1]
    return value


def parse_report(text: str) -> Report:
    pairs = []
    for line in text.splitlines():
        key, sep, value = line.partition(": ")
        if sep:
            pairs.append((key, value))
    return Report(tuple(pairs))
