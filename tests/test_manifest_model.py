import pytest
from tools.manifest import ManifestError, argv, expand, loads, problems

VALID = """<?xml version="1.0" encoding="utf-8" ?>
<encoders generator="AIMP" version="1000" name="Test v1" author="A" info="I">
  <encoder Name="Test" App="tool.exe">
    <description>
      <inputformats type="autogen"><autogen SampleRates="44100;48000" SampleFormats="16" Channels="1;2" /></inputformats>
      <property name="Ext" value=".m4a" />
    </description>
    <presets>
      <preset name="Default" cmdparams="%mode% -b %bitrate% -o %output% -">
        <var name="Mode" cmdparams="%mode%"><val name="A" cmdparams="-a" /><val name="None" cmdparams="" default="1" /></var>
        <var name="Bitrate" cmdparams="%bitrate%"><val name="96" cmdparams="96" /><val name="128" cmdparams="128" default="1" /><val name="256" cmdparams="256" /></var>
      </preset>
    </presets>
  </encoder>
</encoders>"""


def test_valid_manifest_has_no_problems():
    assert problems(loads(VALID)) == []


@pytest.mark.parametrize("old, new, message", [
    ('generator="AIMP"', 'generator="X"', 'generator is not "AIMP"'),
    ('version="1000"', 'version="1"', 'version is not "1000"'),
    ('<property name="Ext" value=".m4a" />', "", "has no Ext"),
    ('App="tool.exe"', 'App="tool"', "App tool does not end in .exe"),
    ('SampleFormats="16"', 'SampleFormats="16;20"', "sample format 20 is not documented"),
    ("-o %output% -", "-o out -", "has no %output%"),
    ("%mode% -b", "%mode% %extra% -b", "macro %extra% has no var"),
    ('cmdparams="%mode% -b %bitrate%', 'cmdparams="-b %bitrate%', "var %mode% is not used"),
    ('<val name="96" cmdparams="96" /><val name="128" cmdparams="128" default="1" /><val name="256" cmdparams="256" />', "", "var %bitrate% has no val"),
    ('cmdparams="96" />', 'cmdparams="96" default="1" />', "more than one default"),
])
def test_problem_is_reported(old, new, message):
    assert old in VALID
    found = problems(loads(VALID.replace(old, new, 1)))
    assert any(message in p for p in found), found


def test_expand_covers_every_choice():
    combos = expand(loads(VALID).encoders[0].presets[0])
    assert len(combos) == 6
    assert {"-a -b 96 -o %output% -", " -b 256 -o %output% -"} <= {c.cmdline for c in combos}


def test_argv_keeps_the_output_whole():
    assert argv(" -b 256 -o %output% -", "/a b/Тест.m4a") == ["-b", "256", "-o", "/a b/Тест.m4a", "-"]


def test_argv_honors_quotes_like_aimp():
    cmdline = "--id 06 \"double quoted\" 'single quoted'  -o %output% -"
    assert argv(cmdline, "/a b/Тест.p06") == ["--id", "06", "double quoted", "single quoted", "-o", "/a b/Тест.p06", "-"]


def test_broken_xml_raises():
    with pytest.raises(ManifestError):
        loads("<encoders>")
