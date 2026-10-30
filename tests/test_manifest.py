from pathlib import Path

from tools.manifest import argv, expand, load, problems
from tools.pins import load_pins

ROOT = Path(__file__).resolve().parent.parent
M = load(ROOT / "package/enc_fdkaac.xml")
PROFILES = {"AAC-LC (FDK)": "2", "HE-AAC (FDK)": "5", "HE-AAC v2 (FDK)": "29"}
LC_RATES = (8000, 11025, 12000, 16000, 22050, 24000, 32000, 44100, 48000, 64000, 88200, 96000)
HE_RATES = (16000, 22050, 24000, 32000, 44100, 48000)
LC_CHANNELS = (1, 2, 6, 8)
# Without IgnoreLength, AIMP writes a stream longer than 4290707456 bytes as two files, the second with "Part2" in its name.
IGNORE_LENGTH = "1"


def test_no_problems():
    assert problems(M) == []


def test_root_attributes():
    assert M.attrs["name"] == f"AAC/M4A Encoder (FDK) v{load_pins(ROOT / 'upstream.json').version}"
    assert M.attrs["author"], "author is empty"


def test_entries():
    assert [e.name for e in M.encoders] == list(PROFILES)
    for e in M.encoders:
        assert (e.app, e.properties.get("Ext"), e.formats.sample_formats) == ("fdkaac-aimp.exe", ".m4a", ("16",))
        assert e.properties.get("IgnoreLength") == IGNORE_LENGTH


def test_rates_and_channels():
    lc, he, he2 = M.encoders
    assert (lc.formats.sample_rates, lc.formats.channels) == (LC_RATES, LC_CHANNELS)
    assert (he.formats.sample_rates, he.formats.channels) == (HE_RATES, (1, 2))
    assert (he2.formats.sample_rates, he2.formats.channels) == (HE_RATES, (2,))


def test_every_entry_has_presets():
    assert all(e.presets for e in M.encoders), "an encoder has no preset"


def test_command_lines():
    for e in M.encoders:
        for c in (c for p in e.presets for c in expand(p)):
            args = argv(c.cmdline, "OUT")
            assert args[-5:] == ["-I", "-S", "-o", "OUT", "-"], c
            assert (args[args.index("-p") + 1] if "-p" in args else "2") == PROFILES[e.name], c
            assert not {"-a", "--afterburner"} & set(args), c
