"""The model of an AIMP command-line encoder manifest, and its checks."""

import itertools
import re
import shlex
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

SAMPLE_FORMATS = ("8", "16", "24", "24i32", "32", "32f")
OUTPUT = "%output%"
_MACRO = re.compile(r"%[^%\s]+%")


class ManifestError(Exception):
    pass


@dataclass(frozen=True)
class Val:
    name: str
    cmdparams: str
    default: bool


@dataclass(frozen=True)
class Var:
    name: str
    macro: str
    vals: tuple[Val, ...]


@dataclass(frozen=True)
class Preset:
    name: str
    cmdparams: str
    default: bool
    vars: tuple[Var, ...]


@dataclass(frozen=True)
class InputFormats:
    sample_rates: tuple[int, ...]
    sample_formats: tuple[str, ...]
    channels: tuple[int, ...]


@dataclass(frozen=True)
class Encoder:
    name: str
    app: str
    debug: bool
    formats: InputFormats
    properties: dict[str, str]
    presets: tuple[Preset, ...]


@dataclass(frozen=True)
class Manifest:
    attrs: dict[str, str]
    encoders: tuple[Encoder, ...]


@dataclass(frozen=True)
class Combination:
    preset: str
    choices: tuple[tuple[str, str], ...]
    cmdline: str


def load(path: Path) -> Manifest:
    return _manifest(_root(Path(path).read_bytes()))


def loads(text: str) -> Manifest:
    return _manifest(_root(text))


def problems(m: Manifest) -> list[str]:
    found = []
    if m.attrs.get("generator") != "AIMP":
        found.append('generator is not "AIMP"')
    if m.attrs.get("version") != "1000":
        found.append('version is not "1000"')
    for e in m.encoders:
        where = f"encoder {e.name}"
        if "Ext" not in e.properties:
            found.append(f"{where} has no Ext")
        if not e.app.endswith(".exe"):
            found.append(f"{where}: App {e.app} does not end in .exe")
        found += [f"{where}: sample format {f} is not documented"
                  for f in e.formats.sample_formats if f not in SAMPLE_FORMATS]
        if sum(p.default for p in e.presets) > 1:
            found.append(f"{where} has more than one default preset")
        for p in e.presets:
            found += _preset_problems(f"{where}, preset {p.name}", p)
    return found


def expand(p: Preset) -> list[Combination]:
    combos = []
    for picks in itertools.product(*(v.vals for v in p.vars)):
        cmdline = p.cmdparams
        for var, val in zip(p.vars, picks):
            cmdline = cmdline.replace(var.macro, val.cmdparams)
        choices = tuple((var.name, val.name) for var, val in zip(p.vars, picks))
        combos.append(Combination(p.name, choices, cmdline))
    return combos


def argv(cmdline: str, output: str) -> list[str]:
    # AIMP splits cmdparams the way a shell does: quotes group words and are removed.
    return [arg.replace(OUTPUT, output) for arg in shlex.split(cmdline)]


def _preset_problems(where: str, p: Preset) -> list[str]:
    found = []
    if OUTPUT not in p.cmdparams:
        found.append(f"{where} has no {OUTPUT}")
    known = {v.macro for v in p.vars}
    found += [f"{where}: macro {m} has no var"
              for m in dict.fromkeys(_MACRO.findall(p.cmdparams)) if m != OUTPUT and m not in known]
    for v in p.vars:
        if v.macro not in p.cmdparams:
            found.append(f"{where}: var {v.macro} is not used")
        if not v.vals:
            found.append(f"{where}: var {v.macro} has no val")
        if sum(x.default for x in v.vals) > 1:
            found.append(f"{where}: var {v.macro} has more than one default val")
    return found


def _root(data: str | bytes) -> ET.Element:
    try:
        return ET.fromstring(data)
    except ET.ParseError as e:
        raise ManifestError(f"XML parse error: {e}") from e


def _manifest(root: ET.Element) -> Manifest:
    if root.tag != "encoders":
        raise ManifestError(f"root element is <{root.tag}> instead of <encoders>")
    return Manifest(_attrs(root), tuple(_encoder(e) for e in root.findall("encoder")))


def _encoder(el: ET.Element) -> Encoder:
    a = _attrs(el)
    where = f"encoder {a.get('name', '')}"
    autogen = el.find("description/inputformats/autogen")
    g = _attrs(autogen) if autogen is not None else {}
    formats = InputFormats(
        _ints(where, "SampleRates", g.get("samplerates")),
        tuple(_items(g.get("sampleformats"))),
        _ints(where, "Channels", g.get("channels")),
    )
    properties = {}
    for prop in el.findall("description/property"):
        pa = _attrs(prop)
        properties[pa.get("name", "")] = pa.get("value", "")
    presets = tuple(_preset(p) for p in el.findall("presets/preset"))
    return Encoder(a.get("name", ""), a.get("app", ""), _flag(a.get("debug")), formats, properties, presets)


def _preset(el: ET.Element) -> Preset:
    a = _attrs(el)
    return Preset(a.get("name", ""), a.get("cmdparams", ""), _flag(a.get("default")),
                  tuple(_var(v) for v in el.findall("var")))


def _var(el: ET.Element) -> Var:
    a = _attrs(el)
    return Var(a.get("name", ""), _macro(a.get("cmdparams", "")), tuple(_val(v) for v in el.findall("val")))


def _val(el: ET.Element) -> Val:
    a = _attrs(el)
    return Val(a.get("name", ""), a.get("cmdparams", ""), _flag(a.get("default")))


def _attrs(el: ET.Element) -> dict[str, str]:
    # The manifests shipped with AIMP write both Name and name on preset.
    return {k.lower(): v for k, v in el.attrib.items()}


def _macro(text: str) -> str:
    # The AIMP documentation writes a bare name here, the shipped manifests write %name%.
    text = text.strip()
    return text if len(text) > 2 and text[0] == text[-1] == "%" else f"%{text}%"


def _flag(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true")


def _items(text: str | None) -> list[str]:
    return [x.strip() for x in (text or "").split(";") if x.strip()]


def _ints(where: str, what: str, text: str | None) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in _items(text))
    except ValueError:
        raise ManifestError(f"{where}: {what} {text!r} is not a list of integers") from None
