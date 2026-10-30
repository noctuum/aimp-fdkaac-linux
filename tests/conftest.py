from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def probe_bin():
    path = ROOT / "build/probe/probe"
    if not path.exists():
        pytest.fail(
            "build/probe/probe is missing: run `mkdir -p build/probe`, then "
            "`cc -std=c11 -O2 -Wall -Wextra -Werror -D_GNU_SOURCE "
            "-DPROBE_VARIANT='\"test\"' -DPROBE_REPORT_DIR='\"\"' "
            "-o build/probe/probe probe/probe.c`"
        )
    return path


@pytest.fixture(scope="session")
def kit():
    path = ROOT / "tmp/probe-kit"
    if not path.is_dir():
        pytest.fail("tmp/probe-kit is missing: run `python3 -I probe/make_kit.py`")
    return path
