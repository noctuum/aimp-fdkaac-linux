import os

import pytest

from tests.helpers import MANIFEST, encode, first
from tools.m4a import aac_payload, stream_info

REFERENCE = os.environ.get("FDKAAC_REFERENCE")
pytestmark = pytest.mark.skipif(not REFERENCE, reason="FDKAAC_REFERENCE is not set")


@pytest.mark.parametrize("index", range(len(MANIFEST.encoders)))
def test_same_payload_as_the_reference(fdkaac_bin, tmp_path, index):
    combo = first(MANIFEST.encoders[index])
    ours, theirs = tmp_path / "ours.m4a", tmp_path / "theirs.m4a"
    assert encode(fdkaac_bin, combo, 44100, 2, 44100 * 3, ours).returncode == 0
    assert encode(REFERENCE, combo, 44100, 2, 44100 * 3, theirs).returncode == 0
    if stream_info(ours).encoder != stream_info(theirs).encoder:
        pytest.skip("the library versions differ")
    assert aac_payload(ours) == aac_payload(theirs)
