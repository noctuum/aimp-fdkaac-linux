from tools.m4a import Smpb, parse_smpb


def test_parse_smpb():
    value = " 00000000 00000800 00000334 00000000000204CC" + " 00000000" * 8
    assert parse_smpb(value) == Smpb(delay=2048, padding=820, length=132300)
