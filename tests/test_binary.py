import re
import subprocess

import pytest

GLIBC_LIBS = {"libc.so.6", "libm.so.6", "libpthread.so.0", "libdl.so.2", "librt.so.1", "ld-linux-x86-64.so.2"}


@pytest.fixture(params=["fdkaac_bin", "wrapper_bin"])
def binary(request):
    return request.getfixturevalue(request.param)


def out(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


def test_needed_is_glibc_only(binary):
    needed = set(re.findall(r"\(NEEDED\)\s+Shared library: \[([^\]]+)\]", out("readelf", "-d", binary)))
    assert needed and needed <= GLIBC_LIBS, needed


def test_glibc_versions_are_at_most_2_28(binary):
    found = {tuple(map(int, v.split("."))) for v in re.findall(r"GLIBC_(\d+(?:\.\d+)+)", out("objdump", "-T", binary))}
    assert found and max(found) <= (2, 28), max(found)


def test_stripped_x86_64(binary):
    text = out("readelf", "-h", "-S", binary)
    assert "Advanced Micro Devices X86-64" in text and ".symtab" not in text


def test_reports_its_version(fdkaac_bin):
    p = subprocess.run([fdkaac_bin, "--help"], capture_output=True)
    assert (p.stdout + p.stderr).decode().splitlines()[0] == "fdkaac 1.0.9"
